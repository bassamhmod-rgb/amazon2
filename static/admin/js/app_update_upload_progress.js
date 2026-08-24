(function () {
  "use strict";

  function createProgressBox(form) {
    var box = document.getElementById("app-update-upload-progress");
    if (box) return box;

    box = document.createElement("div");
    box.id = "app-update-upload-progress";
    box.style.display = "none";
    box.style.margin = "12px 0";
    box.style.padding = "12px";
    box.style.border = "1px solid #d0d7de";
    box.style.borderRadius = "6px";
    box.style.background = "#f6f8fa";

    var label = document.createElement("div");
    label.id = "app-update-upload-progress-label";
    label.textContent = "Uploading update file...";
    label.style.marginBottom = "8px";
    label.style.fontWeight = "600";

    var track = document.createElement("div");
    track.style.height = "14px";
    track.style.background = "#e5e7eb";
    track.style.borderRadius = "999px";
    track.style.overflow = "hidden";

    var bar = document.createElement("div");
    bar.id = "app-update-upload-progress-bar";
    bar.style.width = "0%";
    bar.style.height = "100%";
    bar.style.background = "#0d6efd";
    bar.style.transition = "width 120ms linear";

    track.appendChild(bar);
    box.appendChild(label);
    box.appendChild(track);
    form.parentNode.insertBefore(box, form);
    return box;
  }

  function hasSelectedFile(form) {
    var input = form.querySelector('input[type="file"][name="file"]');
    return input && input.files && input.files.length > 0;
  }

  window.addEventListener("load", function () {
    var form = document.querySelector("form#appupdate_form");
    if (!form) return;

    form.addEventListener("submit", function (event) {
      if (!hasSelectedFile(form)) return;

      event.preventDefault();

      var submitter = event.submitter;
      var formData = new FormData(form);
      if (submitter && submitter.name) {
        formData.append(submitter.name, submitter.value || "");
      }

      var progressBox = createProgressBox(form);
      var label = document.getElementById("app-update-upload-progress-label");
      var bar = document.getElementById("app-update-upload-progress-bar");
      progressBox.style.display = "block";
      label.textContent = "Uploading update file... 0%";
      bar.style.width = "0%";

      var buttons = form.querySelectorAll('input[type="submit"], button[type="submit"]');
      buttons.forEach(function (button) {
        button.disabled = true;
      });

      var xhr = new XMLHttpRequest();
      xhr.open(form.method || "POST", form.action || window.location.href, true);
      xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");

      xhr.upload.addEventListener("progress", function (progressEvent) {
        if (!progressEvent.lengthComputable) {
          label.textContent = "Uploading update file...";
          return;
        }
        var percent = Math.round((progressEvent.loaded / progressEvent.total) * 100);
        label.textContent = "Uploading update file... " + percent + "%";
        bar.style.width = percent + "%";
      });

      xhr.onload = function () {
        if (xhr.status >= 200 && xhr.status < 400) {
          label.textContent = "Upload complete. Saving...";
          bar.style.width = "100%";
          window.location.href = xhr.responseURL || window.location.href;
          return;
        }

        document.open();
        document.write(xhr.responseText);
        document.close();
      };

      xhr.onerror = function () {
        label.textContent = "Upload failed. Please try again.";
        buttons.forEach(function (button) {
          button.disabled = false;
        });
      };

      xhr.send(formData);
    });
  });
})();
