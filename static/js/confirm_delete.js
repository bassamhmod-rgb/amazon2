document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".js-confirm-delete").forEach(btn => {

        btn.addEventListener("click", function (e) {
            e.preventDefault();

            if (!confirm("⚠️ هل أنت متأكد من الحذف؟ لا يمكن التراجع.")) {
                return;
            }

            btn.disabled = true;
            btn.innerText = "جارٍ الحذف...";

            btn.closest("form").submit();
        });

    });
});
