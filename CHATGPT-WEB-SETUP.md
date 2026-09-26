# ChatGPT Web setup (v1.0)

Raise AI v1.0 uses the official `https://chatgpt.com` website. It does not use an OpenAI API key and does not create API charges.

On the tested Galaxy Watch 7 there is no Android System WebView service. Raise AI therefore bundles Mozilla GeckoView and applies a local Wear presentation layer to the official site. Samsung Internet is used only if the bundled engine cannot start.

## First setup on the Watch

1. Open **Raise AI**.
2. Tap **Open RaiseGPT Wear UI**.
3. Allow Raise AI microphone access.
4. Log in to ChatGPT once. GeckoView keeps the site's cookies locally on the Watch.
5. If Google sign-in is refused by the embedded browser, use the email/login method offered by ChatGPT instead.
6. Return to Raise AI and open ChatGPT again.
7. Tap ChatGPT's microphone once.
8. Speak, review the dictated text, and manually press ChatGPT's send button.

## What the Wear layer does

- Removes desktop navigation clutter and enlarges ChatGPT's own prompt, microphone and send controls.
- The large microphone still activates ChatGPT's own website dictation; it is not a separate recorder or API client.
- It deliberately does not start ChatGPT Voice Mode; the intended flow is dictate, review, send.
- It grants web audio capture only to HTTPS pages on `chatgpt.com` / `chat.openai.com`.
- It never reads the answer, copies the login cookie, or calls an undocumented ChatGPT endpoint.
- If OpenAI renames one of the website controls, that control may temporarily lose its large Wear styling while the underlying site remains usable.

Because OpenAI does not provide a Wear OS site layout, a future website change can require an update to the local CSS/selectors.

## Google Home

Gemini is still present as a separate fallback. Use **Test Gemini voice** for spoken Google Home commands or **Open Google Home** for direct controls.
