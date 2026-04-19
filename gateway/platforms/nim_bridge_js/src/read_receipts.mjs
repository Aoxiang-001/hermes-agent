export async function acknowledgeInboundMessage({
  message,
  botAccount,
  messageService,
  conversationService,
  logger = console,
}) {
  const conversationType = Number(message?.conversationType ?? 0);
  if (String(message?.senderId ?? "") === String(botAccount ?? "")) {
    return;
  }

  const conversationId = String(message?.conversationId ?? "");
  if (conversationType === 1 && conversationId) {
    await messageService?.sendP2PMessageReceipt?.(message);
    if (typeof conversationService?.markConversationRead === "function") {
      try {
        await conversationService.markConversationRead(conversationId);
      } catch (error) {
        logger.warn?.(
          `[nim] mark conversation read failed — conversationId: ${conversationId}, error: ${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }
    return;
  }

  if (conversationType === 2 || conversationType === 3) {
    await messageService?.sendTeamMessageReceipts?.([message]);
  }
}
