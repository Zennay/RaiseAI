# Raise AI — inloggen via je Mac

> **Alleen voor de legacy ChatGPT Web-fallback.** Deze Mac-loginroute is niet de huidige fysieke acceptance-route. Voor GitHub issue #34 gebruik je de bevroren Raise AI v1.5.2-handoff van bron `8f719bb273f9b997848864f342598e7df5f090e5` via `bash ./start-frozen-acceptance.command [gateway-profile]`, zoals beschreven in `START-HERE.md`.

De veiligste "login bridge" voor Raise AI is geen cookie-export en geen eigen accountserver.
De Watch blijft zelf ingelogd in de ingebouwde GeckoView-browser; je Mac wordt alleen tijdelijk
gebruikt als groter scherm en toetsenbord via ADB/scrcpy.

## Eenmalig

1. Zet op de Galaxy Watch **Developer options → Wireless debugging** aan.
2. Verbind de Watch met ADB.
3. Installeer optioneel scrcpy op de Mac:
   `brew install scrcpy`
4. Vanuit de RaiseAI-map:
   `bash login-from-mac.command`
5. Rond de normale ChatGPT-login af in het venster op je Mac.
6. Sluit scrcpy. De browserprofiel/cookies blijven lokaal in Raise AI op de Watch.

Raise AI leest, exporteert of uploadt je ChatGPT-cookie niet.

## Waarom zo?

Een browsercookie van telefoon/Mac naar de Watch kopiëren zou onnodig gevoelig en fragiel zijn.
Met ADB-mirroring vul je de officiële login gewoon op de Watch in, maar met het gemak van je
Mac-toetsenbord.

Als een externe OAuth-provider een ingebedde browser weigert, gebruik waar mogelijk de normale
ChatGPT e-mail/loginroute in dezelfde Watch-browser.
