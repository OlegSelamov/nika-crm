window.sfCatalogFilter = {
    kind: document.querySelector('[data-filter-kind].active')?.dataset.filterKind || 'all',
    category: (document.querySelector('[data-filter-category].active')?.dataset.filterCategory || 'all')
        .toLocaleLowerCase('ru-RU')
};
window.sfCategoriesExpanded = false;

function sfRefreshCategoryOverflow(){
    const list = document.getElementById('sfCategoryFilters');
    const toggle = document.getElementById('sfCategoryToggle');
    if(!list || !toggle) return;

    list.classList.toggle('expanded', window.sfCategoriesExpanded);
    toggle.textContent = window.sfCategoriesExpanded ? 'Свернуть' : 'Показать все';

    if(window.sfCategoriesExpanded){
        toggle.hidden = false;
        return;
    }

    requestAnimationFrame(()=>{
        toggle.hidden = list.scrollHeight <= list.clientHeight + 1;
    });
}

function sfSyncCategoryFilters(resetExpansion=false){
    const state = window.sfCatalogFilter;
    const allButton = document.querySelector('[data-all-categories]');
    let selectedCategoryIsAvailable = state.category === 'all';

    document.querySelectorAll('[data-category-kinds]').forEach(button=>{
        const kinds = (button.dataset.categoryKinds || '').split(/\s+/).filter(Boolean);
        const visible = state.kind === 'all' || kinds.includes(state.kind);
        button.hidden = !visible;

        if(visible && button.dataset.filterCategory === state.category){
            selectedCategoryIsAvailable = true;
        }
    });

    if(!selectedCategoryIsAvailable){
        state.category = 'all';
    }

    document.querySelectorAll('[data-filter-category]').forEach(button=>{
        button.classList.toggle(
            'active',
            (button.dataset.filterCategory || 'all').toLocaleLowerCase('ru-RU') === state.category
        );
    });

    if(allButton){
        allButton.textContent = state.kind === 'products'
            ? 'Все товары'
            : state.kind === 'services'
                ? 'Все услуги'
                : 'Все категории';
    }

    if(resetExpansion){
        window.sfCategoriesExpanded = false;
    }
    sfRefreshCategoryOverflow();
}

function sfApplyCatalogFilters(){
    const state = window.sfCatalogFilter;
    const searchInput = document.getElementById('sfLiveSearch');
    const query = (searchInput?.value || '').trim().toLocaleLowerCase('ru-RU');

    let visibleCount = 0;

    document.querySelectorAll('[data-item-card]').forEach(card=>{
        const kind = card.dataset.itemKind || '';
        const category = (card.dataset.itemCategory || '').toLocaleLowerCase('ru-RU');
        const haystack = (card.dataset.search || '').toLocaleLowerCase('ru-RU');

        const kindMatch =
            state.kind === 'all' ||
            kind === state.kind;

        const categoryMatch =
            state.category === 'all' ||
            category === state.category;

        const searchMatch =
            !query ||
            haystack.includes(query);

        const visible = kindMatch && categoryMatch && searchMatch;
        card.style.display = visible ? '' : 'none';

        if(visible) visibleCount++;
    });

    document.querySelectorAll('[data-catalog-section]').forEach(section=>{
        const sectionKind = section.dataset.sectionKind || '';
        const kindAllowed =
            state.kind === 'all' ||
            sectionKind === state.kind;

        const hasVisibleCard = [...section.querySelectorAll('[data-item-card]')]
            .some(card => card.style.display !== 'none');

        section.style.display =
            kindAllowed && hasVisibleCard
                ? ''
                : 'none';
    });

    const empty = document.getElementById('sfSearchEmpty');
    if(empty){
        empty.classList.toggle('show', visibleCount === 0);
    }
}

document.addEventListener('click', event=>{
    const kindButton = event.target.closest('[data-filter-kind]');
    if(kindButton){
        window.sfCatalogFilter.kind = kindButton.dataset.filterKind;

        document.querySelectorAll('[data-filter-kind]').forEach(button=>{
            button.classList.toggle('active', button === kindButton);
        });

        sfSyncCategoryFilters(true);
        sfApplyCatalogFilters();
        return;
    }

    const categoryToggle = event.target.closest('#sfCategoryToggle');
    if(categoryToggle){
        window.sfCategoriesExpanded = !window.sfCategoriesExpanded;
        sfRefreshCategoryOverflow();
        return;
    }

    const categoryButton = event.target.closest('[data-filter-category]');
    if(categoryButton){
        window.sfCatalogFilter.category =
            (categoryButton.dataset.filterCategory || 'all')
                .toLocaleLowerCase('ru-RU');

        document.querySelectorAll('[data-filter-category]').forEach(button=>{
            button.classList.toggle('active', button === categoryButton);
        });

        sfApplyCatalogFilters();
    }
});

// Переопределяем фильтрацию поиска так, чтобы она учитывала
// выбранные тип и категорию одновременно.
window.addEventListener('DOMContentLoaded', ()=>{
    const searchInput = document.getElementById('sfLiveSearch');
    const clearButton = document.getElementById('sfSearchClear');

    if(searchInput){
        searchInput.removeEventListener('input', sfApplySearch);
        searchInput.addEventListener('input', ()=>{
            clearButton?.classList.toggle(
                'show',
                Boolean(searchInput.value.trim())
            );
            sfApplyCatalogFilters();
        });
    }

    if(clearButton){
        const replacement = clearButton.cloneNode(true);
        clearButton.parentNode.replaceChild(replacement, clearButton);

        replacement.addEventListener('click', ()=>{
            searchInput.value = '';
            searchInput.focus();
            replacement.classList.remove('show');
            sfApplyCatalogFilters();
        });
    }

    sfSyncCategoryFilters(true);
    sfApplyCatalogFilters();
});

window.addEventListener('resize', ()=>sfRefreshCategoryOverflow());

let sfIndex = 0;
const sfSlides = [...document.querySelectorAll('.sf-slide')];
const sfDots = [...document.querySelectorAll('.sf-slider-dot')];
let sfTimer = null;

function sfRenderSlider(){
    sfSlides.forEach((el,index)=>el.classList.toggle('active',index===sfIndex));
    sfDots.forEach((el,index)=>el.classList.toggle('active',index===sfIndex));
}
function sfGo(index){
    sfIndex = (index + sfSlides.length) % sfSlides.length;
    sfRenderSlider();
    sfRestart();
}
function sfMove(delta){ sfGo(sfIndex + delta); }
function sfRestart(){
    clearInterval(sfTimer);
    sfTimer = setInterval(()=>sfMove(1),5000);
}
sfRestart();

document.getElementById('storefrontSlider')?.addEventListener(
    'mouseenter',
    ()=>clearInterval(sfTimer)
);
document.getElementById('storefrontSlider')?.addEventListener(
    'mouseleave',
    sfRestart
);
