(function () {
    if (typeof sendCommand !== 'function' || typeof requestAiReply !== 'function') return;

    requestAiReply = async function (text) {
        const pagePath = window.location.pathname.slice(0, 200);

        async function call(url, payload) {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Accept: 'application/json'
                },
                body: JSON.stringify(payload)
            });

            const contentType = response.headers.get('content-type') || '';
            let data = {};
            let rawText = '';

            if (contentType.includes('application/json')) {
                try {
                    data = await response.json();
                } catch (e) {
                    data = {};
                }
            } else {
                try {
                    rawText = (await response.text()).replace(/\s+/g, ' ').trim();
                } catch (e) {
                    rawText = '';
                }
            }

            return {response, data, rawText, contentType};
        }

        let result = await call('/api/ai/chat', {
            message: text,
            conversation_id: aiConversationId,
            page_path: pagePath
        });

        if (result.response.status === 404 || result.response.status === 405) {
            result = await call('/api/agent/command', {text});
        }

        const {response, data, rawText, contentType} = result;

        if (!response.ok) {
            const serverMessage = data.error || data.message;
            if (serverMessage) {
                const error = new Error(serverMessage);
                error.status = response.status;
                throw error;
            }

            let details = rawText;
            if (details) {
                details = details
                    .replace(/<[^>]*>/g, ' ')
                    .replace(/\s+/g, ' ')
                    .trim()
                    .slice(0, 180);
            }

            const statusText = response.statusText ? ` ${response.statusText}` : '';
            const contentHint = contentType && !contentType.includes('application/json')
                ? `, ответ ${contentType.split(';')[0]}`
                : '';
            const suffix = details ? ` — ${details}` : '';

            const error = new Error(`HTTP ${response.status}${statusText}${contentHint}${suffix}`);
            error.status = response.status;
            throw error;
        }

        aiConversationId = data.conversation_id || aiConversationId;

        if (data.action) {
            return {
                reply: await runLegacyAgentAction(data),
                confirmation: null
            };
        }

        return {
            reply: data.reply || data.answer || data.message || data.output_text || 'Готово.',
            confirmation: data.confirmation || null,
            actionStatus: data.action_status || null
        };
    };

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
