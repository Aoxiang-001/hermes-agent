export function encodeJsonl(message) {
  return `${JSON.stringify(message)}\n`;
}

export function decodeJsonl(line) {
  const text = String(line).trim();
  if (!text) {
    throw new Error("empty JSONL line");
  }
  return JSON.parse(text);
}

export function writeMessage(stream, message) {
  stream.write(encodeJsonl(message));
}

export function okResponse(id, result = {}) {
  return {
    type: "response",
    id,
    status: "ok",
    result,
  };
}

export function errorResponse(id, error) {
  return {
    type: "response",
    id,
    status: "error",
    error,
  };
}

export function eventMessage(event, payload) {
  return {
    type: "event",
    event,
    payload,
  };
}
