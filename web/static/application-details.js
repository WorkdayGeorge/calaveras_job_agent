"use strict";

const completeDetailsForm = document.getElementById("complete-details-form");

if (completeDetailsForm) {
  completeDetailsForm.addEventListener("submit", function () {
    const button = document.getElementById("complete-details-button");
    button.disabled = true;
    button.textContent = "Loading Details…";
    button.setAttribute("aria-busy", "true");
  });
}
