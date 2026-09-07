export default function ({data, setStateValue}) {
    if (data.idle) return;
    const key = 'stock-insight:ui:v1';
    const read = () => {
        try { return JSON.parse(localStorage.getItem(key)) || {}; }
        catch { return {}; }
    };
    const write = value => {
        try { localStorage.setItem(key, JSON.stringify(value)); }
        catch { /* Storage may be disabled; the application still works. */ }
    };
    if (!data.ready) {
        setStateValue('loaded', read());
        return;
    }
    write({...read(), preferences: data.preferences, theme: data.theme});
    const route = [data.preferences.page_navigation, data.preferences.market_navigation,
        data.preferences.market_view_navigation].join('|');
    const saved = read().views?.[route] || {};
    let restoring = true;
    let timer;
    const expanders = () => [...document.querySelectorAll('[data-testid="stExpander"] details')];
    const label = details => details.querySelector('summary p')?.textContent.trim();
    const saveView = () => {
        if (restoring) return;
        const current = read();
        const main = document.querySelector('[data-testid="stMain"]');
        const tabs = [...document.querySelectorAll('[role="tablist"]')].map(list =>
            list.querySelector('[aria-selected="true"]')?.textContent.trim());
        const expanded = Object.fromEntries(expanders().filter(item => label(item)).map(item => [label(item), item.open]));
        write({...current, views: {...current.views, [route]: {tabs, expanded, scroll: main?.scrollTop || 0}}});
    };
    const restore = () => {
        const details = expanders();
        if (Object.keys(saved.expanded || {}).some(name => !details.some(item => label(item) === name))) return;
        details.forEach(item => {
            const open = saved.expanded?.[label(item)];
            if (typeof open === 'boolean' && item.open !== open) item.querySelector('summary').click();
        });
        const lists = [...document.querySelectorAll('[role="tablist"]')];
        if (saved.tabs?.length && lists.length < saved.tabs.length) return;
        lists.forEach((list, i) => {
            const target = [...list.querySelectorAll('[role="tab"]')].find(tab => tab.textContent.trim() === saved.tabs?.[i]);
            if (target && target.getAttribute('aria-selected') !== 'true') target.click();
        });
        const main = document.querySelector('[data-testid="stMain"]');
        if (saved.scroll && main && main.scrollHeight - main.clientHeight < saved.scroll) return;
        if (main && saved.scroll) main.scrollTop = saved.scroll;
        restoring = false;
        observer.disconnect();
    };
    const observer = new MutationObserver(restore);
    observer.observe(document.body, {childList: true, subtree: true});
    restore();
    const onScroll = () => { clearTimeout(timer); timer = setTimeout(saveView, 200); };
    const onClick = event => {
        if (event.target.closest('[role="tab"]')) setTimeout(saveView, 50);
        // User interaction takes priority over a pending restoration.
        if (event.isTrusted) { restoring = false; observer.disconnect(); }
    };
    document.addEventListener('scroll', onScroll, true);
    document.addEventListener('click', onClick, true);
    document.addEventListener('toggle', saveView, true);
    window.addEventListener('pagehide', saveView);
    return () => {
        clearTimeout(timer);
        observer.disconnect();
        document.removeEventListener('scroll', onScroll, true);
        document.removeEventListener('click', onClick, true);
        document.removeEventListener('toggle', saveView, true);
        window.removeEventListener('pagehide', saveView);
    };
}
