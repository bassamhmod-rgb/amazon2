/* All browsing/cart changes stay on this device until final confirmation. */
(() => {
    'use strict';
    const element = document.getElementById('local-cart-config');
    if (!element) return;
    const config = JSON.parse(element.textContent);
    const catalogue = new Map((config.products || []).map(p => [p.id, p]));
    let items = [];
    let storageOK = true;
    function read() {
        try {
            const saved = localStorage.getItem(config.key);
            const rows = saved === null ? (config.initialItems || []).map(row => ({...catalogue.get(row.id), ...row})) : JSON.parse(saved);
            if (!Array.isArray(rows)) throw new Error('invalid cart');
            const seen = new Set();
            items = rows.filter(row => row && typeof row.id === 'string' && !seen.has(row.id) &&
                Number.isSafeInteger(row.quantity) && row.quantity > 0 && seen.add(row.id))
                .map(row => ({...row, ...catalogue.get(row.id)}));
        } catch (_) {
            storageOK = false;
            message('تعذّر قراءة السلة المحفوظة. فعّل التخزين المحلي بالمتصفح ثم أعد تحميل الصفحة.');
        }
    }
    function message(text) {
        document.querySelectorAll('#local-cart-message, [data-local-cart-message]').forEach(box => {
            box.textContent = text; box.hidden = !text;
        });
    }
    function save() {
        try { localStorage.setItem(config.key, JSON.stringify(items)); storageOK = true; }
        catch (_) { storageOK = false; message('تعذّر حفظ السلة على الجهاز. لا تغلق الصفحة؛ فعّل التخزين المحلي قبل متابعة الطلب.'); }
    }
    function money(amount) {
        const rate = Number(config.rate);
        const usd = config.currency === 'USD' ? amount : rate > 0 ? amount / rate : null;
        const syp = config.currency === 'USD' ? rate > 0 ? amount * rate : null : amount;
        const parts = [];
        if (config.displayCurrency !== 'SYP' && usd !== null) parts.push(usd.toLocaleString('en-US', {maximumFractionDigits: 2, minimumFractionDigits: 2}) + ' $');
        if (config.displayCurrency !== 'USD' && syp !== null) parts.push(syp.toLocaleString('en-US', {maximumFractionDigits: 0}) + ' ل.س');
        return parts.join(' / ') || amount.toFixed(2) + (config.currency === 'USD' ? ' $' : ' ل.س');
    }
    const total = () => items.reduce((sum, row) => sum + Number(row.price || 0) * row.quantity, 0);
    function node(tag, text, className) {
        const result = document.createElement(tag);
        if (text !== undefined) result.textContent = text;
        if (className) result.className = className;
        return result;
    }
    function button(text, label, action) {
        const result = node('button', text, 'btn btn-outline-primary');
        result.type = 'button'; result.setAttribute('aria-label', label);
        result.addEventListener('click', action);
        return result;
    }
    function quantityControl(row) {
        const control = node('div', undefined, 'local-quantity');
        const input = node('input');
        input.type = 'number'; input.min = '0'; input.step = '1'; input.value = row.quantity;
        input.inputMode = 'numeric'; input.setAttribute('aria-label', 'كمية ' + row.name);
        input.addEventListener('change', () => { change(row.id, Number(input.value)); render(); });
        control.append(button('−', 'نقص كمية ' + row.name, () => change(row.id, row.quantity - 1)), input,
            button('+', 'زيادة كمية ' + row.name, () => change(row.id, row.quantity + 1)));
        return control;
    }
    function change(id, quantity, note) {
        const product = catalogue.get(id) || items.find(row => row.id === id);
        const existing = items.find(row => row.id === id);
        if (!product || !Number.isSafeInteger(quantity) || quantity < 0 || quantity > 2147483647) return;
        if (quantity > (existing ? existing.quantity : 0)) {
            if (config.paused) return message(config.pauseMessage);
            if (!product.sellable) return message('هذا المنتج غير متاح للشراء عبر المتجر.');
            if (!product.unlimited && quantity > product.available) return message('الكمية المطلوبة غير متوفرة: ' + product.name);
        }
        message('');
        if (!quantity) items = items.filter(row => row.id !== id);
        else if (existing) { existing.quantity = quantity; if (note !== undefined) existing.note = note; }
        else items.push({...product, quantity, note: note || ''});
        save(); render();
        return true;
    }
    function render() {
        const count = items.reduce((sum, row) => sum + row.quantity, 0);
        const badge = document.getElementById('cart-count');
        if (badge) { badge.textContent = count; badge.classList.toggle('is-hidden', !count); }
        const bar = document.getElementById('local-cart-bar');
        if (bar) { bar.hidden = !count; bar.textContent = 'السلة (' + count + ') — ' + money(total()); }
        document.querySelectorAll('.add-to-cart-form').forEach(form => {
            const id = form.closest('[data-product-id]').dataset.productId;
            const row = items.find(item => item.id === id);
            const controls = form.querySelector('.local-product-quantity');
            controls.replaceChildren();
            if (row) controls.append(quantityControl(row));
            form.querySelector('[type=submit]').hidden = !!row;
        });
        const list = document.getElementById('local-cart-items');
        if (list) {
            list.replaceChildren();
            if (!count) list.append(node('p', 'السلة فارغة.'));
            items.forEach(row => {
                const line = node('div', undefined, 'local-cart-line');
                const info = node('div');
                info.append(node('strong', row.name || 'منتج غير متاح'), node('div', money(Number(row.price || 0) * row.quantity)));
                if (row.note) info.append(node('small', row.note));
                line.append(info, quantityControl(row), button('حذف', 'حذف ' + row.name, () => change(row.id, 0)));
                list.append(line);
            });
        }
        document.querySelectorAll('[data-local-total]').forEach(el => { el.textContent = money(total()); });
        const required = document.getElementById('local-required-amount');
        if (required) required.textContent = money(total() * Number(config.requiredPercent) / 100);
        const checkout = document.getElementById('local-checkout-link');
        if (checkout) { checkout.setAttribute('aria-disabled', String(!count || !storageOK || config.paused)); }
    }
    read();
    if (config.page === 'success') {
        try {
            const snapshotKey = config.key + ':submitted:' + config.token;
            const submitted = JSON.parse(sessionStorage.getItem(snapshotKey) || 'null');
            if (Array.isArray(submitted)) {
                items = items.map(row => {
                    const sent = submitted.find(item => item.id === row.id);
                    return sent ? {...row, quantity: Math.max(0, row.quantity - sent.quantity)} : row;
                }).filter(row => row.quantity > 0);
                save(); sessionStorage.removeItem(snapshotKey);
            }
        } catch (_) { /* Keep a cart if its submission snapshot cannot be read. */ }
        return;
    }
    const dialog = document.getElementById('local-cart-dialog');
    document.querySelectorAll('[data-open-local-cart]').forEach(trigger => trigger.addEventListener('click', event => {
        event.preventDefault(); read(); render(); dialog.showModal();
    }));
    if (dialog) {
        document.getElementById('local-cart-close').addEventListener('click', () => dialog.close());
        dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
        document.getElementById('local-cart-clear').addEventListener('click', () => { items = []; save(); render(); });
    }
    document.querySelectorAll('.add-to-cart-form').forEach(form => form.addEventListener('submit', event => {
        event.preventDefault(); change(form.closest('[data-product-id]').dataset.productId, 1);
    }));
    const detail = document.getElementById('local-product-form');
    if (detail) detail.addEventListener('submit', event => {
        event.preventDefault();
        const id = detail.dataset.productId;
        const existing = items.find(row => row.id === id);
        const changed = change(id, (existing ? existing.quantity : 0) + Number(detail.elements.quantity.value), detail.elements.item_note.value);
        if (changed && storageOK) message('السلة محفوظة على الجهاز.');
    });
    const checkoutLink = document.getElementById('local-checkout-link');
    if (checkoutLink) checkoutLink.addEventListener('click', event => {
        save();
        if (!items.length || !storageOK || config.paused) {
            event.preventDefault(); message(config.paused ? config.pauseMessage : 'راجع السلة وحفظها قبل المتابعة.');
        }
    });
    // Checkout/review read the same local cart; only the final form carries it.
    const confirm = document.getElementById('local-confirm-form');
    if (confirm) confirm.addEventListener('submit', event => {
        read();
        if (!items.length || !storageOK) { event.preventDefault(); return message('السلة فارغة أو غير قابلة للقراءة. ارجع للمتجر.'); }
        const rows = items.map(row => ({id: row.id, quantity: row.quantity, price: row.price, note: row.note || ''}));
        confirm.elements.local_cart.value = JSON.stringify(rows);
        try { sessionStorage.setItem(config.key + ':submitted:' + confirm.elements.checkout_token.value, JSON.stringify(rows)); }
        catch (_) { event.preventDefault(); return message('تعذّر حفظ بيانات التأكيد على الجهاز. فعّل التخزين ثم حاول مجدداً.'); }
        confirm.querySelector('button[type=submit], button:not([type])').disabled = true;
    });
    if (config.page === 'checkout') {
        const form = document.querySelector('form[enctype]');
        form.addEventListener('submit', event => {
            read();
            if (!items.length || !storageOK) { event.preventDefault(); message('السلة فارغة أو غير قابلة للقراءة. ارجع للمتجر.'); }
        });
    }
    const search = document.getElementById('local-catalog-search');
    if (search) {
        function filter(push) {
            const q = search.elements.q.value.trim().toLocaleLowerCase();
            const category = search.elements.category.value;
            const category2 = search.elements.category2.value;
            let visible = 0;
            document.querySelectorAll('.product-column').forEach(card => {
                const p = catalogue.get(card.dataset.productId);
                const show = p.name.toLocaleLowerCase().includes(q) && (!category || category === p.category) && (!category2 || category2 === p.category2);
                card.hidden = !show; if (show) visible++;
            });
            const empty = document.getElementById('local-catalog-empty');
            if (empty) empty.hidden = visible > 0;
            if (push) {
                const url = new URL(location.href);
                ['q', 'category', 'category2'].forEach(name => {
                    const value = search.elements[name].value;
                    if (value) url.searchParams.set(name, value); else url.searchParams.delete(name);
                });
                history.pushState(null, '', url);
            }
        }
        search.addEventListener('submit', event => { event.preventDefault(); filter(true); });
        search.addEventListener('input', () => filter(false));
        search.addEventListener('change', () => filter(true));
        window.addEventListener('popstate', () => {
            const params = new URL(location.href).searchParams;
            ['q', 'category', 'category2'].forEach(name => { search.elements[name].value = params.get(name) || ''; });
            filter(false);
        });
        filter(false);
    }
    window.addEventListener('storage', event => { if (event.key === config.key) { read(); render(); } });
    window.addEventListener('pageshow', () => {
        read(); render();
        if (confirm) confirm.querySelector('button[type=submit], button:not([type])').disabled = false;
    });
    render();
    if (storageOK) save();
})();
