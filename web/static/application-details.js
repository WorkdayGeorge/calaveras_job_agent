"use strict";

const completeDetailsForm = document.getElementById("complete-details-form");
const completeDetailsButton = document.getElementById("complete-details-button");
const manualDetailsSection = document.getElementById("manual-details-section");
const completeDetailsMessage = document.getElementById("complete-details-message");
const completeDetailsMessageText = document.getElementById("complete-details-message-text");
const jobDescriptionContent = document.getElementById("job-description-content");
const COMPLETE_DETAILS_TIMEOUT_MS = 20000;

function resetCompleteDetailsButton() {
  if (completeDetailsButton) {
    completeDetailsButton.disabled = false;
    completeDetailsButton.textContent = "Show Complete Details";
    completeDetailsButton.removeAttribute("aria-busy");
  }
}

if (completeDetailsForm) {
  completeDetailsForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    completeDetailsButton.disabled = true;
    completeDetailsButton.textContent = "Loading Details…";
    completeDetailsButton.setAttribute("aria-busy", "true");

    const controller = new AbortController();
    const timeout = window.setTimeout(function () {
      controller.abort();
    }, COMPLETE_DETAILS_TIMEOUT_MS);

    try {
      const response = await fetch(completeDetailsForm.action, {
        method: "POST",
        credentials: "same-origin",
        signal: controller.signal,
      });
      window.clearTimeout(timeout);
      if (response.ok) {
        window.location.assign(response.url);
        return;
      }
      throw new Error("Complete details request failed.");
    } catch (error) {
      window.clearTimeout(timeout);
      manualDetailsSection.hidden = false;
      completeDetailsForm.hidden = true;
      completeDetailsMessage.hidden = true;
      completeDetailsMessageText.textContent = "";
      jobDescriptionContent.hidden = true;
      resetCompleteDetailsButton();
    }
  });
}

window.addEventListener("pageshow", resetCompleteDetailsButton);
