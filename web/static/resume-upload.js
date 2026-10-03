"use strict";

const resumeUploadForm = document.getElementById("resume-upload-form");

if (resumeUploadForm) {
  resumeUploadForm.addEventListener("submit", function () {
    const button = document.getElementById("resume-upload-button");
    button.disabled = true;
    button.textContent = "Uploading…";
    button.setAttribute("aria-busy", "true");
  });
}
