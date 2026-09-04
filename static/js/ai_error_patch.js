(function () {
    if (typeof sendCommand !== 'function' || typeof requestAiReply !== 'function') return;

    sendCommand = async function () {
        const input = document.getElementById('agent-input');
        const text = input?.value.trim();
        if (!text || aiSending) return;

        input.value = '';
        appendAiMessage('user', text);
        setAiSending(true);
        appendAiMessage('assistant', 'Nika AI думает…', {typing: true, id: 'aiTypingMessage'});

        try {
            const result = await requestAiReply(text);
            const reply = result.reply;

            document.getElementById('aiTypingMessage')?.remove();
            if (result.actionStatus) {
                document.querySelectorAll('#aiMessages .ai-confirmation').forEach(card => card.remove());
            }
            appendAiMessage('assistant', reply);
            if (result.confirmation) appendAiConfirmation(result.confirmation);
            if (voiceEnabled) speak(reply);
        } catch (error) {
            document.getElementById('aiTypingMessage')?.remove();

            const raw = String(error?.message || '').trim();
            const isNetworkError = !raw || /failed to fetch|networkerror|network request failed|load failed/i.test(raw);
            const message = isNetworkError
                ? 'Не удалось соединиться с сервером Nika AI. Проверьте доступность сервера и повторите запрос.'
                : `Ошибка Nika AI: ${raw}`;

            appendAiMessage('assistant', message);
            console.error('Nika AI error:', error);
        } finally {
            setAiSending(false);
            input?.focus();
        }
    };
})();
