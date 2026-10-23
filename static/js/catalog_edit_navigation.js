document.querySelectorAll('[data-edit-url]').forEach((row) => {
    row.style.cursor = 'pointer';
    row.addEventListener('click', (event) => {
        if (event.target.closest('a, button, input, select, textarea, form')) return;
        if (window.getSelection()?.toString()) return;
        window.location.assign(row.dataset.editUrl);
    });
    row.addEventListener('keydown', (event) => {
        if (event.target !== row || event.key !== 'Enter') return;
        event.preventDefault();
        window.location.assign(row.dataset.editUrl);
    });
});

const displayOrder = document.querySelector('form[data-select-display-order] input[name="display_order"]');
if (displayOrder) {
    displayOrder.type = 'text';
    displayOrder.inputMode = 'numeric';
    displayOrder.pattern = '[0-9]+';
    displayOrder.addEventListener('focus', () => displayOrder.select());
    requestAnimationFrame(() => {
        displayOrder.focus();
        displayOrder.select();
    });
}
