#!/usr/bin/env node
import process from "node:process";
import readline from "node:readline";

import {
  buildConversationId,
  normalizeTarget,
  parseBridgeConfig,
  toInboundMessage,
} from "./src/config.mjs";
import {
  decodeJsonl,
  errorResponse,
  eventMessage,
  okResponse,
  writeMessage,
} from "./src/protocol.mjs";
import { acknowledgeInboundMessage } from "./src/read_receipts.mjs";

let runtime = null;

function writeStderr(args) {
  const text = args
    .map((value) => {
      if (typeof value === "string") {
        return value;
      }
      try {
        return JSON.stringify(value);
      } catch {
        return String(value);
      }
    })
    .join(" ");
  process.stderr.write(`${text}\n`);
}

console.log = (...args) => writeStderr(args);
console.info = (...args) => writeStderr(args);
console.warn = (...args) => writeStderr(args);
console.error = (...args) => writeStderr(args);

function emit(message) {
  writeMessage(process.stdout, message);
}

async function cleanupRuntime() {
  if (!runtime) {
    return;
  }

  try {
    await runtime.loginService.logout();
  } catch {}

  try {
    await runtime.nim.destroy?.();
  } catch {}

  runtime = null;
}

async function handleConnect(id, params) {
  await cleanupRuntime();

  const config = parseBridgeConfig(params?.config ?? {});
  const mod = await import("@yxim/nim-bot");
  const NIM = mod.default ?? mod;
  const nim = new NIM(
    {
      appkey: config.credentials.appKey,
      apiVersion: "v2",
      debugLevel: config.debug ? "debug" : "off",
    },
    undefined,
  );

  const loginService = nim.V2NIMLoginService;
  const messageService = nim.V2NIMMessageService;
  const messageCreator = nim.V2NIMMessageCreator;
  const conversationService =
    nim.V2NIMConversationService ?? nim.V2NIMLocalConversationService;

  if (!loginService || !messageService || !messageCreator) {
    throw new Error("NIM SDK V2 services are unavailable");
  }

  messageService.on("onReceiveMessages", (messages = []) => {
    for (const message of messages) {
      void acknowledgeInboundMessage({
        message,
        botAccount: config.credentials.account,
        messageService,
        conversationService,
        logger: console,
      }).catch((error) => {
        console.warn("Failed to acknowledge inbound NIM message", error);
      });
      emit(
        eventMessage(
          "message",
          toInboundMessage(message, config.credentials.account),
        ),
      );
    }
  });

  await loginService.login(config.credentials.account, config.credentials.token, {
    aiBot: 2,
  });

  runtime = {
    nim,
    loginService,
    messageService,
    messageCreator,
    conversationService,
    config,
  };

  emit(
    okResponse(id, {
      connected: true,
      account: config.credentials.account,
    }),
  );
}

async function handleDisconnect(id) {
  await cleanupRuntime();
  emit(okResponse(id, { connected: false }));
}

async function handleHealth(id) {
  emit(
    okResponse(id, {
      connected: Boolean(runtime),
      account: runtime?.config?.credentials?.account ?? null,
    }),
  );
}

async function handleSendMessage(id, params) {
  if (!runtime) {
    throw new Error("bridge is not connected");
  }

  const target = normalizeTarget(params?.chat_id, params?.session_type);
  const conversationId = buildConversationId(
    runtime.nim,
    target.id,
    target.sessionType,
  );
  const message = runtime.messageCreator.createTextMessage(String(params?.text ?? ""));

  if (!message) {
    throw new Error("failed to create text message");
  }

  const result = await new Promise((resolve, reject) => {
    let settled = false;
    const clientMessageId = message.messageClientId;

    const listener = (sentMessage) => {
      if (sentMessage?.messageClientId !== clientMessageId || settled) {
        return;
      }
      if (sentMessage?.sendingState === 3) {
        return;
      }

      settled = true;
      runtime.messageService.off?.("onSendMessage", listener);
      const errorCode = sentMessage?.messageStatus?.errorCode;
      const failed =
        sentMessage?.sendingState === 2 ||
        (sentMessage?.sendingState === 1 && errorCode !== 200);

      if (failed) {
        reject(
          new Error(
            sentMessage?.messageStatus?.errorDesc ?? `send failed (${errorCode ?? "unknown"})`,
          ),
        );
        return;
      }

      resolve({
        message_id: String(sentMessage?.messageServerId ?? ""),
        client_message_id: String(sentMessage?.messageClientId ?? ""),
      });
    };

    runtime.messageService.on("onSendMessage", listener);
    runtime.messageService
      .sendMessage(message, conversationId, {})
      .catch((error) => {
        if (settled) {
          return;
        }
        settled = true;
        runtime.messageService.off?.("onSendMessage", listener);
        reject(error);
      });

    setTimeout(() => {
      if (settled) {
        return;
      }
      settled = true;
      runtime.messageService.off?.("onSendMessage", listener);
      reject(new Error("send_message timed out"));
    }, 30000);
  });

  emit(okResponse(id, result));
}

async function handleRequest(message) {
  const id = String(message?.id ?? "");
  const method = message?.method;

  try {
    if (method === "connect") {
      await handleConnect(id, message?.params);
      return;
    }
    if (method === "disconnect") {
      await handleDisconnect(id);
      return;
    }
    if (method === "health") {
      await handleHealth(id);
      return;
    }
    if (method === "send_message") {
      await handleSendMessage(id, message?.params);
      return;
    }
    throw new Error(`unsupported method: ${method}`);
  } catch (error) {
    emit(errorResponse(id, error instanceof Error ? error.message : String(error)));
  }
}

const rl = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

rl.on("line", async (line) => {
  try {
    const message = decodeJsonl(line);
    if (message?.type !== "request") {
      return;
    }
    await handleRequest(message);
  } catch (error) {
    emit(
      errorResponse(
        "",
        error instanceof Error ? error.message : String(error),
      ),
    );
  }
});

process.on("SIGINT", async () => {
  await cleanupRuntime();
  process.exit(0);
});

process.on("SIGTERM", async () => {
  await cleanupRuntime();
  process.exit(0);
});
