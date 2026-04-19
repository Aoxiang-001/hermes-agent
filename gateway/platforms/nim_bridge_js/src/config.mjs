function parseNimToken(value) {
  const raw = String(value ?? "").trim();
  if (!raw) {
    return null;
  }
  let parts = null;
  if (raw.includes("|")) {
    const items = raw.split("|");
    if (items.length >= 3) {
      parts = [items[0], items[1], items.slice(2).join("|")];
    }
  } else {
    const firstDash = raw.indexOf("-");
    const secondDash = firstDash >= 0 ? raw.indexOf("-", firstDash + 1) : -1;
    if (firstDash > 0 && secondDash > firstDash + 1) {
      parts = [
        raw.slice(0, firstDash),
        raw.slice(firstDash + 1, secondDash),
        raw.slice(secondDash + 1),
      ];
    }
  }
  if (!parts || parts.some((part) => !part)) {
    return null;
  }
  return {
    appKey: parts[0],
    account: parts[1],
    token: parts[2],
  };
}

export function parseBridgeConfig(raw) {
  const credentials = raw?.credentials ?? {};
  const shorthand = parseNimToken(raw?.nim_token ?? raw?.nimToken);
  const resolved = shorthand ?? {
    appKey: String(credentials.app_key ?? credentials.appKey ?? ""),
    account: String(credentials.account ?? ""),
    token: String(credentials.token ?? ""),
  };

  if (!resolved.appKey || !resolved.account || !resolved.token) {
    throw new Error("bridge credentials are incomplete");
  }

  return {
    credentials: resolved,
    debug: Boolean(raw?.debug),
    mediaMaxMb: Number(raw?.media_max_mb ?? raw?.mediaMaxMb ?? 30),
    homeChannel: raw?.home_channel ?? raw?.homeChannel ?? null,
  };
}

export function normalizeTarget(chatId, fallbackSessionType = "p2p") {
  const raw = String(chatId ?? "").trim();
  if (!raw) {
    throw new Error("chat_id is required");
  }

  if (raw.startsWith("team:") || raw.startsWith("group:")) {
    return {
      id: raw.slice(raw.indexOf(":") + 1),
      sessionType: "team",
    };
  }

  if (raw.startsWith("user:") || raw.startsWith("nim:")) {
    return {
      id: raw.slice(raw.indexOf(":") + 1),
      sessionType: "p2p",
    };
  }

  return {
    id: raw,
    sessionType: fallbackSessionType,
  };
}

export function buildConversationId(nim, targetId, sessionType) {
  const util = nim?.V2NIMConversationIdUtil;
  if (util) {
    if (sessionType === "team") {
      return util.teamConversationId(targetId) || `0|2|${targetId}`;
    }
    if (sessionType === "superTeam") {
      return util.superTeamConversationId(targetId) || `0|3|${targetId}`;
    }
    return util.p2pConversationId(targetId) || `0|1|${targetId}`;
  }

  const typeNumber = sessionType === "team" ? 2 : sessionType === "superTeam" ? 3 : 1;
  return `0|${typeNumber}|${targetId}`;
}

export function parseConversationId(conversationId) {
  const parts = String(conversationId ?? "").split("|");
  if (parts.length < 3) {
    return { sessionType: "p2p", targetId: "" };
  }
  const typeNumber = Number(parts[1]);
  return {
    sessionType: typeNumber === 2 ? "team" : typeNumber === 3 ? "superTeam" : "p2p",
    targetId: parts[2],
  };
}

export function toInboundMessage(message, botAccount) {
  const parsed = parseConversationId(message?.conversationId);
  const pushIds = message?.pushConfig?.forcePushAccountIds ?? [];
  const mentioned = pushIds.includes(botAccount);
  const typeMap = {
    0: "text",
    1: "image",
    2: "audio",
    3: "video",
    6: "file",
  };

  return {
    message_id: String(message?.messageServerId ?? message?.messageClientId ?? ""),
    client_message_id: String(message?.messageClientId ?? ""),
    session_type: parsed.sessionType,
    sender_id: String(message?.senderId ?? ""),
    sender_name: message?.senderName ?? null,
    target_id: String(message?.receiverId ?? parsed.targetId ?? ""),
    conversation_name: null,
    text: message?.text ?? "",
    message_type: typeMap[message?.messageType] ?? "unknown",
    force_push_account_ids: pushIds,
    mentioned,
    mention_all: false,
    from_self: String(message?.senderId ?? "") === String(botAccount ?? ""),
    raw: message,
  };
}
