document.addEventListener("DOMContentLoaded", function () {

    const isGlobal = document.getElementById("id_is_global");
    const channel = document.getElementById("id_channel");
    const targetStoreRow = document.querySelector(".form-row.field-target_store");
    const targetClientRow = document.querySelector(".form-row.field-target_accounting_client");

    function toggleTargetFields() {
        if (isGlobal.checked) {
            targetStoreRow.style.display = "none";
            targetClientRow.style.display = "none";
            return;
        }

        targetStoreRow.style.display = "block";

        if (channel.value === "accounting") {
            targetClientRow.style.display = "block";
        } else {
            targetClientRow.style.display = "none";
        }
    }

    if (isGlobal && channel) {
        toggleTargetFields();
        isGlobal.addEventListener("change", toggleTargetFields);
        channel.addEventListener("change", toggleTargetFields);
    }
});
