import test from "node:test";
import assert from "node:assert/strict";

import { acknowledgeInboundMessage } from "../src/read_receipts.mjs";

test("acknowledgeInboundMessage marks p2p conversation as read and sends receipt", async () => {
  const calls = [];
  const message = {
    conversationType: 1,
    conversationId: "0|1|user-1",
    senderId: "user-1",
  };

  await acknowledgeInboundMessage({
    message,
    botAccount: "bot-1",
    logger: { info() {} },
    conversationService: {
      async markConversationRead(conversationId) {
        calls.push(["markConversationRead", conversationId]);
      },
    },
    messageService: {
      async sendP2PMessageReceipt(receiptMessage) {
        calls.push(["sendP2PMessageReceipt", receiptMessage]);
      },
    },
  });

  assert.deepEqual(calls, [
    ["sendP2PMessageReceipt", message],
    ["markConversationRead", "0|1|user-1"],
  ]);
});

test("acknowledgeInboundMessage still sends p2p receipt when markConversationRead fails", async () => {
  const calls = [];
  const message = {
    conversationType: 1,
    conversationId: "0|1|user-1",
    senderId: "user-1",
  };

  await acknowledgeInboundMessage({
    message,
    botAccount: "bot-1",
    logger: { info() {}, warn() {} },
    conversationService: {
      async markConversationRead() {
        calls.push(["markConversationRead"]);
        throw new Error("V2CloudConversation is not enabled");
      },
    },
    messageService: {
      async sendP2PMessageReceipt(receiptMessage) {
        calls.push(["sendP2PMessageReceipt", receiptMessage]);
      },
    },
  });

  assert.deepEqual(calls, [
    ["sendP2PMessageReceipt", message],
    ["markConversationRead"],
  ]);
});

test("acknowledgeInboundMessage skips self messages", async () => {
  const calls = [];

  await acknowledgeInboundMessage({
    message: {
      conversationType: 1,
      conversationId: "0|1|bot-1",
      senderId: "bot-1",
    },
    botAccount: "bot-1",
    logger: { info() {} },
    conversationService: {
      async markConversationRead() {
        calls.push("markConversationRead");
      },
    },
    messageService: {
      async sendP2PMessageReceipt() {
        calls.push("sendP2PMessageReceipt");
      },
    },
  });

  assert.deepEqual(calls, []);
});

test("acknowledgeInboundMessage sends team receipts for team messages", async () => {
  const calls = [];
  const message = {
    conversationType: 2,
    conversationId: "0|2|team-1",
    senderId: "user-1",
  };

  await acknowledgeInboundMessage({
    message,
    botAccount: "bot-1",
    logger: { info() {} },
    conversationService: {
      async markConversationRead(conversationId) {
        calls.push(["markConversationRead", conversationId]);
      },
    },
    messageService: {
      async sendTeamMessageReceipts(messages) {
        calls.push(["sendTeamMessageReceipts", messages]);
      },
    },
  });

  assert.deepEqual(calls, [
    ["sendTeamMessageReceipts", [message]],
  ]);
});
