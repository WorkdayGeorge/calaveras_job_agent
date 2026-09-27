(() => {
  if (globalThis.__calaverasApplicationAssistantLoaded) return;
  globalThis.__calaverasApplicationAssistantLoaded = true;

  const SENSITIVE = /social security|ssn|date of birth|birth date|dob|gender|sex|race|ethnic|disability|veteran|protected class|signature|certif(y|ication)|attest|agree to|terms and conditions|privacy policy|criminal|background check/i;
  const SUBMIT = /submit|send application|complete application|finish application/i;

  function text(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function descriptor(element) {
    const parts = [
      element.getAttribute("aria-label"),
      element.getAttribute("placeholder"),
      element.getAttribute("autocomplete"),
      element.name,
      element.id
    ];
    if (element.id) {
      const label = document.querySelector(`label[for="${CSS.escape(element.id)}"]`);
      if (label) parts.push(label.innerText);
    }
    const wrappingLabel = element.closest("label");
    if (wrappingLabel) parts.push(wrappingLabel.innerText);
    const fieldset = element.closest("fieldset");
    if (fieldset) parts.push(fieldset.querySelector("legend")?.innerText);
    const group = element.closest('[role="group"], [role="radiogroup"]');
    if (group) parts.push(group.getAttribute("aria-label"));
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy) {
      for (const id of labelledBy.split(/\s+/)) {
        parts.push(document.getElementById(id)?.innerText);
      }
    }
    return text(parts.filter(Boolean).join(" ")).slice(0, 600);
  }

  function splitName(fullName) {
    const parts = text(fullName).split(" ").filter(Boolean);
    const suffixes = new Set(["jr", "jr.", "sr", "sr.", "ii", "iii", "iv"]);
    const suffix = suffixes.has((parts.at(-1) || "").toLowerCase()) ? parts.pop() : "";
    return {
      first: parts.shift() || "",
      last: [parts.pop() || "", suffix].filter(Boolean).join(" "),
      middle: parts.join(" ")
    };
  }

  function fieldValue(label, profile) {
    const identity = profile.identity || {};
    const answers = profile.standard_answers || {};
    const name = splitName(identity.full_name);
    const valueRules = [
      [/linkedin/, identity.linkedin_url],
      [/(e-?mail)/, identity.email],
      [/(mobile|cell|telephone|phone)/, identity.phone],
      [/(address.*(line )?2|address2|suite|apartment|apt\.?|unit)/, identity.address_line_2],
      [/(street address|address.*(line )?1|address1)/, identity.address_line_1],
      [/(postal|zip)/, identity.postal_code],
      [/(city|town)/, identity.city],
      [/(state|province)/, identity.state],
      [/(country)/, identity.country],
      [/(first|given).*name/, name.first],
      [/(middle).*name/, name.middle],
      [/(last|family|surname).*name/, name.last],
      [/(full|legal|candidate|applicant).*name|^name$/, identity.full_name],
      [/(authori[sz]ed|eligible).*(work|employment)/, answers.authorized_to_work],
      [/(sponsor|visa)/, answers.requires_sponsorship],
      [/(relocat)/, answers.willing_to_relocate],
      [/(available|start date|when.*start)/, answers.available_start_date],
      [/(desired|expected).*(salary|pay|compensation)|salary expectation/, answers.desired_salary],
      [/(remote|work arrangement|work location preference)/, answers.remote_preference]
    ];
    for (const [pattern, value] of valueRules) {
      if (pattern.test(label.toLowerCase())) return text(value);
    }
    return "";
  }

  function mark(element) {
    element.style.outline = "2px solid #16a34a";
    element.style.outlineOffset = "1px";
    element.dataset.calaverasFilled = "true";
  }

  function setTextValue(element, value) {
    const prototype = element instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
    if (setter) setter.call(element, value);
    else element.value = value;
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    mark(element);
  }

  function chooseSelect(element, value) {
    const wanted = value.toLowerCase();
    const aliases = wanted === "yes" ? ["yes", "true"] : wanted === "no" ? ["no", "false"] : [wanted];
    const option = [...element.options].find(item => {
      const candidate = `${item.value} ${item.textContent}`.toLowerCase().trim();
      return aliases.some(alias =>
        candidate === alias
        || candidate.startsWith(`${alias} `)
        || (wanted !== "yes" && wanted !== "no" && candidate.includes(alias))
      );
    });
    if (!option) return false;
    element.value = option.value;
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    mark(element);
    return true;
  }

  function chooseRadio(element, value) {
    const name = element.name;
    if (!name) return false;
    const wanted = value.toLowerCase();
    const radios = [...document.querySelectorAll(`input[type="radio"][name="${CSS.escape(name)}"]`)];
    const choice = radios.find(radio => {
      const candidate = `${radio.value} ${descriptor(radio)}`.toLowerCase();
      return wanted === "yes" ? /\byes\b|\btrue\b/.test(candidate) : wanted === "no" ? /\bno\b|\bfalse\b/.test(candidate) : candidate.includes(wanted);
    });
    if (!choice) return false;
    choice.click();
    mark(choice);
    return true;
  }

  function base64Bytes(value) {
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return bytes;
  }

  function uploadResume(element, resume) {
    if (!resume || typeof DataTransfer === "undefined") return false;
    const file = new File([base64Bytes(resume.base64)], resume.filename, { type: resume.mimeType });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    element.files = transfer.files;
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    mark(element);
    return true;
  }

  function fillApplication(profile, resume) {
    let filled = 0;
    let skipped = 0;
    const handledRadioGroups = new Set();
    const elements = [...document.querySelectorAll("input, textarea, select")];
    for (const element of elements) {
      if (element.disabled || element.readOnly || element.dataset.calaverasFilled === "true") continue;
      const label = descriptor(element);
      const inputType = (element.type || "").toLowerCase();
      if (!label || SENSITIVE.test(label) || SUBMIT.test(label) || ["hidden", "password", "submit", "button", "image", "reset"].includes(inputType)) {
        skipped += 1;
        continue;
      }
      if (inputType === "file") {
        if (/resume|curriculum|\bcv\b/i.test(label) && uploadResume(element, resume)) filled += 1;
        else skipped += 1;
        continue;
      }
      const value = fieldValue(label, profile);
      if (!value || value === "review") {
        skipped += 1;
        continue;
      }
      if (inputType === "radio") {
        if (handledRadioGroups.has(element.name)) continue;
        handledRadioGroups.add(element.name);
        if (chooseRadio(element, value)) filled += 1;
        else skipped += 1;
      } else if (element instanceof HTMLSelectElement) {
        if (chooseSelect(element, value)) filled += 1;
        else skipped += 1;
      } else if (["checkbox"].includes(inputType)) {
        skipped += 1;
      } else {
        setTextValue(element, value);
        filled += 1;
      }
    }
    return { filled, skipped };
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "CALAVERAS_FILL_APPLICATION") return false;
    try {
      sendResponse(fillApplication(message.profile, message.resume));
    } catch (error) {
      sendResponse({ filled: 0, skipped: 0, error: error.message });
    }
    return true;
  });
})();
