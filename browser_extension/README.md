# Calaveras Application Assistant Chrome Extension

This Manifest V3 extension fills common job-application fields from the signed-in
user's approved Calaveras Job Agent profile. It never submits an application.

## Install for MVP testing

1. In Chrome, open `chrome://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked**.
4. Select this `browser_extension` directory.
5. In the Calaveras Job Agent, open **Application Assistant**, save the reusable
   answers, and create an extension access token.
6. Open the extension, paste the token, and select **Save & Connect**.

## Use

Open an employer's application form, select the extension, choose an approved
resume, and select **Fill This Application**. Green-outlined fields were filled.
Review every field and answer all skipped questions before submitting manually.

The token is stored in Chrome extension storage and expires after 90 days. Revoke
it from the web application if the computer or token is lost.
