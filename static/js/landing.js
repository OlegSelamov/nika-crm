(() => {
    "use strict";

    const header = document.querySelector("[data-site-header]");
    const nav = document.getElementById("siteNavigation");
    const navToggle = document.querySelector("[data-nav-toggle]");

    const updateHeader = () => {
        header?.classList.toggle("is-scrolled", window.scrollY > 18);
    };

    updateHeader();
    window.addEventListener("scroll", updateHeader, { passive: true });

    const closeNavigation = () => {
        nav?.classList.remove("is-open");
        navToggle?.setAttribute("aria-expanded", "false");
        document.body.classList.remove("nav-open");
    };

    navToggle?.addEventListener("click", () => {
        const willOpen = !nav?.classList.contains("is-open");
        nav?.classList.toggle("is-open", willOpen);
        navToggle.setAttribute("aria-expanded", String(willOpen));
        document.body.classList.toggle("nav-open", willOpen);
    });

    nav?.querySelectorAll("a").forEach(link => link.addEventListener("click", closeNavigation));
    document.addEventListener("keydown", event => {
        if (event.key === "Escape") closeNavigation();
    });

    document.addEventListener("click", event => {
        if (!nav?.classList.contains("is-open")) return;
        if (nav.contains(event.target) || navToggle?.contains(event.target)) return;
        closeNavigation();
    });

    const revealItems = [...document.querySelectorAll(".reveal")];
    revealItems.forEach(item => {
        const delay = Number(item.dataset.delay || 0);
        item.style.setProperty("--reveal-delay", `${delay}ms`);
    });

    if ("IntersectionObserver" in window) {
        const revealObserver = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (!entry.isIntersecting) return;
                entry.target.classList.add("is-visible");
                revealObserver.unobserve(entry.target);
            });
        }, { threshold: 0.12, rootMargin: "0px 0px -45px" });

        revealItems.forEach(item => revealObserver.observe(item));
    } else {
        revealItems.forEach(item => item.classList.add("is-visible"));
    }

    const animateCounter = element => {
        const target = Number(element.dataset.counter || 0);
        const duration = 900;
        const startedAt = performance.now();

        const tick = now => {
            const progress = Math.min((now - startedAt) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            element.textContent = String(Math.round(target * eased));
            if (progress < 1) requestAnimationFrame(tick);
        };

        requestAnimationFrame(tick);
    };

    const counters = document.querySelectorAll("[data-counter]");
    if ("IntersectionObserver" in window) {
        const counterObserver = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (!entry.isIntersecting) return;
                animateCounter(entry.target);
                counterObserver.unobserve(entry.target);
            });
        }, { threshold: 0.55 });
        counters.forEach(counter => counterObserver.observe(counter));
    } else {
        counters.forEach(animateCounter);
    }

    const heroDemo = document.querySelector(".hero-demo");
    const voiceDemoButton = document.querySelector("[data-voice-demo]");
    const voiceState = document.querySelector("[data-voice-state]");
    const demoCommand = document.querySelector("[data-demo-command]");
    const demoResult = document.querySelector("[data-demo-result]");
    let demoRunning = false;
    let demoIndex = 0;

    const demoScenarios = [
        {
            command: "«Добавь Кока-Колу, хлеб и молоко. Оплата наличными»",
            result: "Фискальный чек готов"
        },
        {
            command: "«Найди клиента Арман и создай ему продажу»",
            result: "Клиент и продажа найдены"
        },
        {
            command: "«Покажи выручку и прибыль за сегодня»",
            result: "Аналитика открыта"
        },
        {
            command: "«Открой склад и покажи низкие остатки»",
            result: "Найдено 4 позиции"
        }
    ];

    const wait = milliseconds => new Promise(resolve => window.setTimeout(resolve, milliseconds));

    voiceDemoButton?.addEventListener("click", async () => {
        if (demoRunning) return;
        demoRunning = true;
        heroDemo?.classList.add("is-playing");
        voiceDemoButton.disabled = true;

        const scenario = demoScenarios[demoIndex % demoScenarios.length];
        demoIndex += 1;
        if (demoCommand) demoCommand.textContent = scenario.command;
        if (voiceState) voiceState.textContent = "Слышу команду…";
        await wait(900);
        if (voiceState) voiceState.textContent = "Выполняю…";
        await wait(850);
        if (demoResult) demoResult.textContent = scenario.result;
        if (voiceState) voiceState.textContent = "Готово. Нажмите ещё раз";

        heroDemo?.classList.remove("is-playing");
        voiceDemoButton.disabled = false;
        demoRunning = false;
    });

    const phoneCommands = [
        {
            command: "«Открой раздел продаж»",
            title: "Открываю продажи",
            description: "Раздел уже на экране"
        },
        {
            command: "«Добавь в корзину хлеб и молоко»",
            title: "Товары добавлены",
            description: "Корзина готова к оплате"
        },
        {
            command: "«Пробей наличными»",
            title: "Жду подтверждения",
            description: "После него сформирую чек"
        },
        {
            command: "«Покажи прибыль за сегодня»",
            title: "Аналитика открыта",
            description: "Показатели рассчитаны"
        }
    ];

    const phoneCommand = document.querySelector("[data-phone-command]");
    const phoneTitle = document.querySelector("[data-phone-title]");
    const phoneDescription = document.querySelector("[data-phone-description]");
    const commandButtons = document.querySelectorAll("[data-command-index]");

    commandButtons.forEach(button => {
        button.addEventListener("click", () => {
            const index = Number(button.dataset.commandIndex || 0);
            const item = phoneCommands[index];
            if (!item) return;

            commandButtons.forEach(current => current.classList.toggle("is-active", current === button));
            if (phoneCommand) phoneCommand.textContent = item.command;
            if (phoneTitle) phoneTitle.textContent = item.title;
            if (phoneDescription) phoneDescription.textContent = item.description;
        });
    });

    document.querySelectorAll(".faq-item button").forEach(button => {
        button.addEventListener("click", () => {
            const item = button.closest(".faq-item");
            const willOpen = !item?.classList.contains("is-open");

            document.querySelectorAll(".faq-item.is-open").forEach(openItem => {
                if (openItem === item) return;
                openItem.classList.remove("is-open");
                openItem.querySelector("button")?.setAttribute("aria-expanded", "false");
            });

            item?.classList.toggle("is-open", willOpen);
            button.setAttribute("aria-expanded", String(willOpen));
        });
    });
})();
