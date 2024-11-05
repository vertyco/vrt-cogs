Seamless translation between two languages in one channel. Or manual translation to various languages.<br/><br/>Fluent uses google translate by default, with [Flowery](https://flowery.pw/) as a fallback.<br/><br/>Fluent also supports the [Deepl](https://www.deepl.com/pro#developer) tranlsation api.<br/>1. Register your free Deepl account **[Here](https://www.deepl.com/pro#developer)**.<br/>2. Obtain your API key **[Here](https://www.deepl.com/account/summary)**.<br/>3. Set your API key with:<br/>`[p]set api deepl key YOUR_KEY_HERE`<br/><br/>If a deepl key is set, it will use that before falling back to google translate and then flowery.

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
## [p]fluent add
Add a channel and languages to translate between<br/>

Tip: Language 1 is the first to be converted. For example, if you expect most of the conversation to be<br/>
in english, then make english language 2 to use less api calls.<br/>
 - Usage: `[p]fluent add <language1> <language2> [channel=None]`
## [p]fluent view
View all fluent channels<br/>
 - Usage: `[p]fluent view`
## [p]fluent remove
Remove a channel from Fluent<br/>
 - Usage: `[p]fluent remove [channel=None]`
 - Aliases: `delete, del, and rem`
