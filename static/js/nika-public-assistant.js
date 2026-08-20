(function () {
    "use strict";

    const page = document.body.dataset.nikaAssistantPage || "landing";
    const authenticated = document.body.dataset.nikaAssistantAuthenticated === "true";

    const configs = {
        landing: {
            label: "Знакомство с Nika",
            title: "Расскажу о Nika Business",
            welcome: "Спросите о возможностях, тарифах, продажах, складе, кассе или AI-ассистенте.",
            suggestions: ["Что умеет Nika?", "Расскажи о тарифах", "Как работает голосовой ассистент?"],
            action: ["Начать бесплатно", "/register?plan=business"]
        },
        login: {
            label: "Помощь со входом",
            title: "Помогу войти в систему",
            welcome: "Подскажу, как войти, зарегистрировать компанию или что делать, если данные не подходят.",
            suggestions: ["Как войти?", "У меня ещё нет аккаунта", "Не подходит пароль"],
            action: ["Создать аккаунт", "/register?plan=business"]
        },
        register: {
            label: "Помощь с регистрацией",
            title: "Помогу создать компанию",
            welcome: "Объясню поля регистрации, выбранный тариф и бесплатный пробный период.",
            suggestions: ["Какие поля обязательны?", "Когда потребуется оплата?", "Какой тариф выбран?"],
            action: ["Уже есть аккаунт — войти", "/login"]
        },
        onboarding: {
            label: "Настройка бизнеса",
            title: "Настроим Nika вместе",
            welcome: "Спросите о текущем шаге. Я помогу выбрать тип бизнеса, модули и стартовые настройки.",
            suggestions: ["Помоги выбрать тип бизнеса", "Какие модули мне нужны?", "Что можно изменить позже?"]
        },
        onboarding_finish: {
            label: "Завершение настройки",
            title: "Nika готова к запуску",
            welcome: "Помогу понять подключённые разделы и выбрать первое действие после настройки.",
            suggestions: ["С чего начать работу?", "Как добавить товары?", "Как провести первую продажу?"],
            action: ["Открыть рабочий стол", "/dashboard"]
        }
    };

    const config = configs[page] || configs.landing;
    let conversationId = null;
    let sending = false;
    let recognition = null;
    let voiceRequest = false;

    function createElement(tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text) element.textContent = text;
        return element;
    }

    function buildAssistant() {
        const root = createElement("div", "nika-public-assistant");
        root.innerHTML = `
            <button class="nika-public-fab" type="button" aria-label="Открыть Nika AI" aria-expanded="false">
                <span class="nika-public-fab__icon">
                    <img src="/static/icons/assistant-top.png" alt="">
                    <i class="nika-public-fab__pulse" aria-hidden="true"></i>
                </span>
                <span class="nika-public-fab__copy"><b>Nika AI</b><small></small></span>
            </button>
            <section class="nika-public-panel" role="dialog" aria-label="Nika AI">
                <div class="nika-public-panel__head">
                    <div class="nika-public-panel__brand">
                        <img src="/static/icons/assistant-top.png" alt="">
                        <div><b>Nika AI</b><small></small></div>
                    </div>
                    <button class="nika-public-panel__close" type="button" aria-label="Закрыть">×</button>
                </div>
                <div class="nika-public-messages" aria-live="polite">
                    <div class="nika-public-welcome">
                        <b></b><p></p><div class="nika-public-suggestions"></div>
                    </div>
                </div>
                <div class="nika-public-action-wrap"></div>
                <div class="nika-public-composer">
                    <div class="nika-public-composer__box">
                        <button class="nika-public-mic" type="button" title="Говорить">🎙</button>
                        <textarea rows="1" maxlength="1200" placeholder="Спросите Nika…"></textarea>
                        <button class="nika-public-send" type="button" title="Отправить">➤</button>
                    </div>
                </div>
            </section>`;

        document.body.appendChild(root);

        const fab = root.querySelector(".nika-public-fab");
        const panel = root.querySelector(".nika-public-panel");
        const close = root.querySelector(".nika-public-panel__close");
        const input = root.querySelector("textarea");
        const send = root.querySelector(".nika-public-send");
        const mic = root.querySelector(".nika-public-mic");

        root.querySelector(".nika-public-fab__copy small").textContent = config.label;
        root.querySelector(".nika-public-panel__brand small").textContent = config.label;
        root.querySelector(".nika-public-welcome b").textContent = config.title;
        root.querySelector(".nika-public-welcome p").textContent = config.welcome;

        const suggestions = root.querySelector(".nika-public-suggestions");
        config.suggestions.forEach(prompt => {
            const button = createElement("button", "nika-public-suggestion", prompt);
            button.type = "button";
            button.addEventListener("click", () => submitMessage(prompt));
            suggestions.appendChild(button);
        });

        if (config.action) {
            const action = createElement("a", "nika-public-panel__action", config.action[0]);
            action.href = config.action[1];
            root.querySelector(".nika-public-action-wrap").appendChild(action);
        }

        function setOpen(open) {
            panel.classList.toggle("open", open);
            fab.classList.toggle("is-open", open);
            fab.setAttribute("aria-expanded", open ? "true" : "false");
            sessionStorage.setItem("nikaStandaloneAssistantOpen", open ? "1" : "0");
            if (open) setTimeout(() => input.focus(), 80);
        }

        fab.addEventListener("click", () => setOpen(!panel.classList.contains("open")));
        close.addEventListener("click", () => setOpen(false));
        send.addEventListener("click", () => submitMessage(input.value));
        input.addEventListener("keydown", event => {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submitMessage(input.value);
            }
        });
        mic.addEventListener("click", startVoiceInput);

        document.addEventListener("keydown", event => {
            if (event.key === "Escape") setOpen(false);
        });
        document.addEventListener("click", event => {
            if (panel.classList.contains("open") && !root.contains(event.target)) setOpen(false);
        });

        if (sessionStorage.getItem("nikaStandaloneAssistantOpen") === "1") setOpen(true);

        async function submitMessage(rawText) {
            const text = String(rawText || "").trim();
            if (!text || sending) return;
            input.value = "";
            appendMessage("user", text);
            sending = true;
            send.disabled = true;
            const typing = appendMessage("assistant", "Nika думает…", true);

            try {
                const reply = authenticated
                    ? await requestAuthenticatedReply(text)
                    : publicReply(text);
                typing.remove();
                appendMessage("assistant", reply);
                if (voiceRequest) speak(reply);
            } catch (error) {
                typing.remove();
                appendMessage("assistant", authenticated
                    ? "Не удалось связаться с Nika. Попробуйте ещё раз."
                    : "Не получилось обработать вопрос. Выберите одну из подсказок выше.");
            } finally {
                voiceRequest = false;
                sending = false;
                send.disabled = false;
                input.focus();
            }
        }

        function appendMessage(role, text, typing) {
            const messages = root.querySelector(".nika-public-messages");
            const message = createElement(
                "div",
                `nika-public-message nika-public-message--${role}${typing ? " nika-public-message--typing" : ""}`,
                text
            );
            messages.appendChild(message);
            messages.scrollTop = messages.scrollHeight;
            return message;
        }

        async function requestAuthenticatedReply(text) {
            const response = await fetch("/api/ai/chat", {
                method: "POST",
                headers: {"Content-Type": "application/json", "Accept": "application/json"},
                body: JSON.stringify({
                    message: text,
                    conversation_id: conversationId,
                    page_path: window.location.pathname.slice(0, 200)
                })
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || "AI unavailable");
            conversationId = data.conversation_id || conversationId;
            return data.reply || "Готово.";
        }

        function startVoiceInput() {
            const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!Recognition) {
                appendMessage("assistant", "Голосовой ввод не поддерживается этим браузером. Можно написать вопрос текстом.");
                return;
            }
            if (recognition) {
                try { recognition.stop(); } catch (error) {}
            }
            recognition = new Recognition();
            recognition.lang = "ru-RU";
            recognition.continuous = false;
            recognition.interimResults = false;
            mic.classList.add("listening");
            recognition.onresult = event => {
                const text = event.results[0][0].transcript.trim();
                voiceRequest = true;
                submitMessage(text);
            };
            recognition.onerror = () => mic.classList.remove("listening");
            recognition.onend = () => mic.classList.remove("listening");
            recognition.start();
        }
    }

    function publicReply(rawText) {
        const text = String(rawText || "").toLowerCase().replace(/ё/g, "е");

        if (page === "landing") {
            if (/тариф|цен|стоим/.test(text)) return "Есть три тарифа: Старт — 9 900 тенге, Бизнес — 19 900 тенге, Профи — 29 900 тенге в месяц. Начать можно бесплатно, без оплаты при регистрации.";
            if (/голос|ассист|ai|ника/.test(text)) return "Nika понимает голосовые и текстовые команды: открывает разделы, ищет данные, помогает собрать продажу и готовит действия. Изменения выполняются только после подтверждения.";
            if (/касс|чек|продаж/.test(text)) return "Nika помогает собрать корзину, выбрать способ оплаты, передать оплату в Kaspi POS, пробить фискальный чек через reKassa и отправить его клиенту.";
            if (/склад|остат/.test(text)) return "В системе есть остатки, приход, списание и движения товаров. Nika может найти дефицит и подготовить складскую операцию.";
            return "Nika Business объединяет продажи, склад, клиентов, документы, аналитику, кассу, WhatsApp и AI-ассистента. Спросите о тарифах или конкретной возможности.";
        }

        if (page === "login") {
            if (/нет аккаун|регист|созда/.test(text)) return "Нажмите «Создать аккаунт». Вы выберете тариф, заполните данные владельца и компании, после чего Nika проведёт через настройку бизнеса.";
            if (/парол|не подходит|забыл/.test(text)) return "Сначала проверьте раскладку клавиатуры и логин. Если пароль всё равно не подходит, обратитесь к владельцу или администратору вашей организации для восстановления доступа.";
            return "Введите логин и пароль, выданные владельцем организации. Если компании ещё нет, перейдите к регистрации.";
        }

        if (page === "register") {
            const selectedPlan = document.querySelector('input[name="plan"]')?.value || "business";
            const planNames = {start: "Старт", business: "Бизнес", pro: "Профи"};
            if (/тариф|выбран/.test(text)) return `Сейчас выбран тариф «${planNames[selectedPlan] || "Бизнес"}». После регистрации его можно будет изменить в настройках подписки.`;
            if (/оплат|бесплат|пробн/.test(text)) return "Оплата при регистрации не требуется. Сначала действует бесплатный 14-дневный пробный период.";
            if (/обяз|поле|заполн/.test(text)) return "Обязательно укажите название компании, логин и пароль. Реквизиты, БИН или ИИН и адрес можно дополнить позже.";
            return "Заполните данные владельца и компании. После создания аккаунта Nika поможет настроить тип бизнеса, модули и рабочие разделы.";
        }

        return config.welcome;
    }

    function speak(text) {
        if (!("speechSynthesis" in window)) return;
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(String(text || "").slice(0, 700));
        utterance.lang = "ru-RU";
        utterance.rate = .96;
        window.speechSynthesis.speak(utterance);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", buildAssistant, {once: true});
    } else {
        buildAssistant();
    }
})();
