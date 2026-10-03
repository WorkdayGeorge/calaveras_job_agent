"use strict";

const completeDetailsForm = document.getElementById("complete-details-form");
const completeDetailsButton = document.getElementById("complete-details-button");

function resetCompleteDetailsButton() {
  if (completeDetailsButton) {
    completeDetailsButton.disabled = false;
    completeDetailsButton.textContent = "Show Complete Details";
    completeDetailsButton.removeAttribute("aria-busy");
  }
}

if (completeDetailsForm) {
  completeDetailsForm.addEventListener("submit", function () {
    completeDetailsButton.disabled = true;
    completeDetailsButton.textContent = "Loading Details…";
    completeDetailsButton.setAttribute("aria-busy", "true");
  });
}

window.addEventListener("pageshow", resetCompleteDetailsButton);
