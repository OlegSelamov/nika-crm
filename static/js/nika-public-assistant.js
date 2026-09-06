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

    const FLOW_KEY = "nikaAssistantFlow";

    function loadFlow() {
        try { return JSON.parse(sessionStorage.getItem(FLOW_KEY) || "{}") || {}; }
        catch (_) { return {}; }
    }

    function saveFlow(patch) {
        const next = {...loadFlow(), ...patch, updatedAt: Date.now()};
        sessionStorage.setItem(FLOW_KEY, JSON.stringify(next));
        return next;
    }

    function clearFlow() {
        sessionStorage.removeItem(FLOW_KEY);
    }

    function navigateTo(url) {
        if (!url) return;
        sessionStorage.setItem("nikaStandaloneAssistantOpen", "1");
        window.location.href = url;
    }

    function setInputValue(name, value) {
        const input = document.querySelector('[name="' + name + '"]');
        if (!input) return false;
        input.value = value;
        input.dispatchEvent(new Event("input", {bubbles: true}));
        input.dispatchEvent(new Event("change", {bubbles: true}));
        return true;
    }

    function runUiAction(result) {
        if (!result || typeof result !== "object") return;
        if (result.action === "redirect" && result.url) {
            setTimeout(() => navigateTo(result.url), 550);
        } else if (result.action === "open_drawer" && result.target) {
            setTimeout(() => {
                if (typeof window.openSystemDrawer === "function") window.openSystemDrawer(result.target);
            }, 250);
        }
    }

    function yes(text) {
        return /^(да|давай|хочу|начать|начинаем|поехали|конечно|ок|окей|ага)\b/i.test(String(text || "").trim());
    }

    function skip(text) {
        return /пропуст|позже|нет|не сейчас|не надо/i.test(String(text || ""));
    }

    function businessTypeFromText(text) {
        const value = String(text || "").toLowerCase().replace(/ё/g, "е");
        if (/магаз|розниц|продукт|торгов/.test(value)) return "retail";
        if (/кафе|кофейн|ресторан|общепит/.test(value)) return "cafe";
        if (/салон|красот|парикмах|барбер/.test(value)) return "beauty";
        if (/опт|поставщик|дистриб/.test(value)) return "wholesale";
        if (/услуг|сервис|ремонт|консульт/.test(value)) return "services";
        return null;
    }

    function startRegistrationFlow() {
        saveFlow({stage: "register", expected: "director"});
        return {
            reply: "Хорошо. Начнём регистрацию. Сначала скажите ваше ФИО — я подставлю его в форму.",
            action: page === "register" ? null : "redirect",
            url: page === "register" ? null : "/register?plan=business"
        };
    }

    function handleRegistrationFlow(text) {
        if (page !== "register") return null;
        let flow = loadFlow();
        if (flow.stage !== "register") {
            if (!/помоги|проведи|регист|запол|начать/i.test(text)) return null;
            flow = saveFlow({stage: "register", expected: "director"});
            return {reply: "Проведу вас по регистрации. Как вас зовут? Назовите ФИО владельца."};
        }

        const value = String(text || "").trim();
        const expected = flow.expected || "director";
        if (expected === "director") {
            setInputValue("director", value);
            saveFlow({expected: "phone"});
            return {reply: "Заполнила ФИО. Теперь назовите номер телефона."};
        }
        if (expected === "phone") {
            setInputValue("phone", value);
            saveFlow({expected: "username"});
            return {reply: "Телефон записала. Какой логин хотите использовать для входа?"};
        }
        if (expected === "username") {
            setInputValue("username", value.replace(/\s+/g, ""));
            saveFlow({expected: "password"});
            return {reply: "Логин готов. Теперь придумайте пароль минимум из 6 символов. Пароль я никуда не сохраняю — только подставлю в поле формы."};
        }
        if (expected === "password") {
            setInputValue("password", value);
            saveFlow({expected: "company"});
            if (typeof window.goNext === "function") window.goNext();
            return {reply: "Пароль подставлен и не сохранён. Теперь скажите название компании."};
        }
        if (expected === "company") {
            setInputValue("name", value);
            saveFlow({expected: "bin"});
            return {reply: "Компания указана. Назовите БИН или ИИН. Если хотите заполнить позже — скажите «пропустить»."};
        }
        if (expected === "bin") {
            if (!skip(value)) setInputValue("bin", value.replace(/\s+/g, ""));
            saveFlow({expected: "address"});
            return {reply: "Хорошо. Теперь адрес компании. Его тоже можно пропустить."};
        }
        if (expected === "address") {
            if (!skip(value)) setInputValue("address", value);
            saveFlow({expected: "review"});
            if (typeof window.goNext === "function") {
                window.goNext();
                setTimeout(() => window.goNext(), 100);
            }
            return {reply: "Основные данные готовы. Банковские реквизиты можно добавить позже. Я открыла итог регистрации. Проверьте данные и скажите «создать компанию»."};
        }
        if (expected === "review" && /созда|готов|подтверж|регистр/i.test(value)) {
            saveFlow({stage: "onboarding", expected: "business_type"});
            const form = document.getElementById("registerForm");
            if (form) setTimeout(() => form.requestSubmit(), 250);
            return {reply: "Создаю компанию. После регистрации я продолжу настройку уже как помощник владельца."};
        }
        return {reply: "Сейчас проверьте итоговые данные. Если всё верно, скажите «создать компанию»."};
    }

    function setOnboardingChoice(name, value) {
        const hidden = document.querySelector('input[name="' + name + '"]');
        if (!hidden) return false;
        hidden.value = value ? "1" : "0";
        const group = document.querySelector('.yn[data-name="' + name + '"]');
        if (group) {
            group.querySelectorAll("button").forEach(button => {
                button.classList.toggle("active", button.dataset.value === (value ? "1" : "0"));
            });
        }
        return true;
    }

    function handleOnboardingFlow(text) {
        if (page !== "onboarding") return null;
        let flow = loadFlow();
        if (flow.stage !== "onboarding") {
            if (!/помоги|настро|проведи|начать/i.test(text)) return null;
            flow = saveFlow({stage: "onboarding", expected: "business_type"});
        }

        const value = String(text || "").trim();
        const expected = flow.expected || "business_type";
        if (expected === "business_type") {
            const type = businessTypeFromText(value);
            if (!type) return {reply: "Какой у вас бизнес: магазин, услуги, кафе, салон или оптовая торговля?"};
            const radio = document.querySelector('input[name="business_type"][value="' + type + '"]');
            if (radio) {
                radio.checked = true;
                document.querySelectorAll('input[name="business_type"]').forEach(x => x.closest(".option")?.classList.toggle("selected", x === radio));
            }
            saveFlow({expected: "sell_type", businessType: type});
            if (typeof window.next === "function") window.next();
            return {reply: "Поняла. Вы продаёте товары, услуги или и то и другое?"};
        }
        if (expected === "sell_type") {
            const normalized = value.toLowerCase();
            const products = /товар|продукт|оба|и то/i.test(normalized);
            const services = /услуг|оба|и то/i.test(normalized);
            if (!products && !services) return {reply: "Скажите: товары, услуги или оба варианта."};
            setOnboardingChoice("sells_products", products);
            setOnboardingChoice("sells_services", services);
            saveFlow({expected: "stock"});
            return {reply: products ? "Нужен учёт склада и остатков?" : "Хорошо. Склад для такого сценария обычно не нужен. Скажите «да», если всё же хотите вести остатки."};
        }
        if (expected === "stock") {
            setOnboardingChoice("has_stock", yes(value));
            saveFlow({expected: "continue_setup"});
            if (typeof window.next === "function") window.next();
            return {reply: "Основной тип работы настроен. Дальше уточним сотрудников, кассу, бухгалтерию и остальные возможности. Продолжаем?"};
        }
        if (expected === "continue_setup" && yes(value)) {
            clearFlow();
            return {reply: "Продолжаем. На текущем шаге выберите, есть ли сотрудники. Я остаюсь рядом и могу объяснить любой пункт."};
        }
        return null;
    }

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
                let result = handleRegistrationFlow(text) || handleOnboardingFlow(text);
                if (!result) {
                    result = authenticated
                        ? await requestAuthenticatedReply(text)
                        : publicReply(text);
                }
                if (typeof result === "string") result = {reply: result};
                typing.remove();
                const reply = result?.reply || "Готово.";
                appendMessage("assistant", reply);
                runUiAction(result);
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
            return data;
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
            const detectedBusiness = businessTypeFromText(rawText);
            if (detectedBusiness) {
                const names = {retail:"магазин", services:"бизнес услуг", cafe:"кафе или общепит", beauty:"салон", wholesale:"оптовую торговлю"};
                saveFlow({stage:"lead", businessType:detectedBusiness});
                return "Поняла: у вас " + (names[detectedBusiness] || "бизнес") + ". Nika сможет подобрать подходящие модули и провести настройку. Если хотите начать, скажите «давай зарегистрируемся».";
            }
            if ((loadFlow().stage === "lead" && yes(rawText)) || /зарегистр|начать.*работ|создать.*компан/i.test(text)) {
                return startRegistrationFlow();
            }
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
            if (/проведи|заполни|помоги.*регист/.test(text)) return startRegistrationFlow();
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
