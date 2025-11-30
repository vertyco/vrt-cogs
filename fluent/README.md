Seamless translation between two languages in one channel. Or manual translation to various languages.<br/><br/>Fluent uses google translate by default, with [Flowery](https://flowery.pw/) as a fallback.<br/><br/>Fluent also supports Deeple and OpenAI for translations.<br/>Use `[p]fluent openai` and `[p]fluent deepl` to set your keys.<br/><br/>Fallback order (If translation fails):<br/>1. OpenAI<br/>2. Deepl<br/>3. Google Translate<br/>4. Flowery

# [p]serverlocale
Check the current server's locale<br/>
 - Usage: `[p]serverlocale`
# [p]translate (Hybrid Command)
Translate a message<br/>
 - Usage: `[p]translate <to_language> [message]`
 - Slash Usage: `/translate <to_language> [message]`
# [p]fluent
Base command<br/>
 - Usage: `[p]fluent`
 - Restricted to: `MOD`
## [p]fluent removebutton
Remove a translation button from a message<br/>
 - Usage: `[p]fluent removebutton <message> <target_lang>`
## [p]fluent openai
Set an openai key for translations<br/>
 - Usage: `[p]fluent openai`
 - Restricted to: `BOT_OWNER`
## [p]fluent viewbuttons
View all translation buttons<br/>
 - Usage: `[p]fluent viewbuttons`
## [p]fluent deepl
Set a deepl key for translations<br/>
 - Usage: `[p]fluent deepl`
 - Restricted to: `BOT_OWNER`
## [p]fluent remove
Remove a channel from Fluent<br/>
 - Usage: `[p]fluent remove [channel=None]`
 - Aliases: `delete, del, and rem`
## [p]fluent resetbuttontranslations
Reset the translations for saved buttons, to force a re-translation<br/>
 - Usage: `[p]fluent resetbuttontranslations`
## [p]fluent view
View all fluent channels<br/>
 - Usage: `[p]fluent view`
## [p]fluent add
Add a channel and languages to translate between<br/>

Tip: Language 1 is the first to be converted. For example, if you expect most of the conversation to be<br/>
in english, then make english language 2 to use less api calls.<br/>
 - Usage: `[p]fluent add <language1> <language2> [channel=None]`
## [p]fluent only
Add a channel that translates all messages to a single language<br/>

Unlike `[p]fluent add` which translates between two languages,<br/>
this translates all messages to the specified target language<br/>
regardless of the source language.<br/>
 - Usage: `[p]fluent only <target_language> [channel=None]`
## [p]fluent addbutton
Add a translation button to a message<br/>
 - Usage: `[p]fluent addbutton <message> <target_lang> <button_text>`
