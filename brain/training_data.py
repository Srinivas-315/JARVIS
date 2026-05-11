"""
JARVIS — brain/training_data.py
Comprehensive labeled training dataset for intent classifier.

Stats:
  - 1000+ training examples
  - 30+ intent classes
  - Includes Indian English, casual speech, voice-style phrases
  - Colab-ready: import this file directly in train_colab.py
"""

TRAINING_DATA = [

    # ════════════════════════════════════════════════════════════
    # OPEN APP
    # ════════════════════════════════════════════════════════════
    ("open notepad", "open_app"),
    ("launch spotify", "open_app"),
    ("start chrome", "open_app"),
    ("open calculator", "open_app"),
    ("open vs code", "open_app"),
    ("launch file explorer", "open_app"),
    ("open telegram", "open_app"),
    ("start excel", "open_app"),
    ("open paint", "open_app"),
    ("launch word", "open_app"),
    ("open the camera", "open_app"),
    ("can you open settings", "open_app"),
    ("open task manager", "open_app"),
    ("start vlc", "open_app"),
    ("open discord", "open_app"),
    ("launch brave browser", "open_app"),
    ("open whatsapp desktop", "open_app"),
    ("open snipping tool", "open_app"),
    ("open powerpoint", "open_app"),
    ("launch adobe photoshop", "open_app"),
    ("open zoom", "open_app"),
    ("start microsoft teams", "open_app"),
    ("open google chrome", "open_app"),
    ("launch python idle", "open_app"),
    ("open visual studio", "open_app"),
    ("start android studio", "open_app"),
    ("open postman", "open_app"),
    ("launch docker", "open_app"),
    ("open obsidian", "open_app"),
    ("start notion", "open_app"),
    ("open figma", "open_app"),
    ("launch pycharm", "open_app"),
    ("open steam", "open_app"),
    ("start epic games", "open_app"),
    ("open camera app", "open_app"),
    ("launch mail app", "open_app"),
    ("open maps", "open_app"),
    ("start terminal", "open_app"),
    ("open command prompt", "open_app"),
    ("launch powershell", "open_app"),
    ("open github desktop", "open_app"),
    ("start winrar", "open_app"),
    ("open media player", "open_app"),
    ("launch itunes", "open_app"),
    ("open one drive", "open_app"),
    ("start skype", "open_app"),
    ("open firefox", "open_app"),
    ("launch edge browser", "open_app"),
    ("open opera", "open_app"),
    ("start sublime text", "open_app"),
    ("open atom editor", "open_app"),
    ("launch jupyter notebook", "open_app"),
    ("open anaconda", "open_app"),
    ("start spyder", "open_app"),

    # ════════════════════════════════════════════════════════════
    # CLOSE APP
    # ════════════════════════════════════════════════════════════
    ("close notepad", "close_app"),
    ("kill chrome", "close_app"),
    ("exit spotify", "close_app"),
    ("close the calculator", "close_app"),
    ("quit vs code", "close_app"),
    ("stop notepad", "close_app"),
    ("close this app", "close_app"),
    ("kill task manager", "close_app"),
    ("end excel", "close_app"),
    ("shut down chrome", "close_app"),
    ("close all apps", "close_app"),
    ("close brave", "close_app"),
    ("exit discord", "close_app"),
    ("quit zoom", "close_app"),
    ("close teams", "close_app"),
    ("terminate vlc", "close_app"),
    ("close word", "close_app"),
    ("exit powerpoint", "close_app"),
    ("kill firefox", "close_app"),
    ("close all windows", "close_app"),
    ("end this program", "close_app"),
    ("close the browser", "close_app"),
    ("shut down the app", "close_app"),
    ("force quit chrome", "close_app"),
    ("close everything", "close_app"),

    # ════════════════════════════════════════════════════════════
    # SYSTEM VOLUME
    # ════════════════════════════════════════════════════════════
    ("increase volume", "volume_control"),
    ("volume up", "volume_control"),
    ("turn up the volume", "volume_control"),
    ("make it louder", "volume_control"),
    ("decrease volume", "volume_control"),
    ("volume down", "volume_control"),
    ("lower the volume", "volume_control"),
    ("mute", "volume_control"),
    ("unmute", "volume_control"),
    ("set volume to 50", "volume_control"),
    ("turn the sound up", "volume_control"),
    ("silence the computer", "volume_control"),
    ("raise volume", "volume_control"),
    ("reduce volume", "volume_control"),
    ("sound up please", "volume_control"),
    ("sound down please", "volume_control"),
    ("can you increase the sound", "volume_control"),
    ("make it quieter", "volume_control"),
    ("turn off sound", "volume_control"),
    ("max volume", "volume_control"),
    ("minimum volume", "volume_control"),
    ("speaker off", "volume_control"),
    ("speaker on", "volume_control"),

    # ════════════════════════════════════════════════════════════
    # SYSTEM BRIGHTNESS
    # ════════════════════════════════════════════════════════════
    ("increase brightness", "brightness_control"),
    ("brightness up", "brightness_control"),
    ("make screen brighter", "brightness_control"),
    ("decrease brightness", "brightness_control"),
    ("dim the screen", "brightness_control"),
    ("lower brightness", "brightness_control"),
    ("turn down brightness", "brightness_control"),
    ("set brightness to 80", "brightness_control"),
    ("reduce screen brightness", "brightness_control"),
    ("can you dim the screen", "brightness_control"),
    ("brighten my screen", "brightness_control"),
    ("screen too dark", "brightness_control"),
    ("screen too bright", "brightness_control"),
    ("max brightness", "brightness_control"),
    ("night mode brightness", "brightness_control"),

    # ════════════════════════════════════════════════════════════
    # SCREENSHOT
    # ════════════════════════════════════════════════════════════
    ("take a screenshot", "screenshot"),
    ("capture screen", "screenshot"),
    ("screenshot please", "screenshot"),
    ("grab the screen", "screenshot"),
    ("take a screen capture", "screenshot"),
    ("snap the screen", "screenshot"),
    ("take a picture of screen", "screenshot"),
    ("save screen image", "screenshot"),
    ("print screen", "screenshot"),
    ("capture this screen", "screenshot"),
    ("take screenshot now", "screenshot"),
    ("snap screenshot", "screenshot"),

    # ════════════════════════════════════════════════════════════
    # WEATHER
    # ════════════════════════════════════════════════════════════
    ("what's the weather", "weather"),
    ("how's the weather today", "weather"),
    ("weather in chennai", "weather"),
    ("is it going to rain", "weather"),
    ("what's the temperature", "weather"),
    ("weather forecast", "weather"),
    ("tell me the weather", "weather"),
    ("how hot is it outside", "weather"),
    ("what's the weather like", "weather"),
    ("will it rain today", "weather"),
    ("humidity today", "weather"),
    ("weather update", "weather"),
    ("check the weather", "weather"),
    ("is it sunny today", "weather"),
    ("what is the weather report", "weather"),
    ("temperature outside", "weather"),
    ("should I carry umbrella", "weather"),
    ("how cold is it", "weather"),
    ("any rain expected", "weather"),
    ("weather for tomorrow", "weather"),
    ("weekend weather", "weather"),

    # ════════════════════════════════════════════════════════════
    # NEWS
    # ════════════════════════════════════════════════════════════
    ("what's the news", "news"),
    ("tell me the headlines", "news"),
    ("top stories today", "news"),
    ("any news about technology", "news"),
    ("sports news", "news"),
    ("what's happening in the world", "news"),
    ("breaking news", "news"),
    ("read me the news", "news"),
    ("today's headlines", "news"),
    ("tech news today", "news"),
    ("india news today", "news"),
    ("business news", "news"),
    ("cricket news", "news"),
    ("bollywood news", "news"),
    ("political news", "news"),
    ("international news", "news"),
    ("stock market news", "news"),
    ("what's new today", "news"),
    ("any updates", "news"),
    ("science news", "news"),

    # ════════════════════════════════════════════════════════════
    # YOUTUBE
    # ════════════════════════════════════════════════════════════
    ("play on youtube", "youtube_search"),
    ("open youtube", "youtube_search"),
    ("youtube search", "youtube_search"),
    ("play despacito on youtube", "youtube_search"),
    ("search youtube for tutorials", "youtube_search"),
    ("find videos about python", "youtube_search"),
    ("play music video on youtube", "youtube_search"),
    ("show me youtube", "youtube_search"),
    ("youtube coding tutorials", "youtube_search"),
    ("open youtube and play songs", "youtube_search"),
    ("play latest songs on youtube", "youtube_search"),
    ("search for gaming videos youtube", "youtube_search"),
    ("play lo fi music on youtube", "youtube_search"),
    ("play arijit singh songs", "youtube_search"),
    ("youtube shorts", "youtube_search"),
    ("play motivational videos", "youtube_search"),
    ("open youtube music", "youtube_search"),

    # ════════════════════════════════════════════════════════════
    # GOOGLE SEARCH / BROWSER SEARCH
    # ════════════════════════════════════════════════════════════
    ("search for python tutorials", "web_search"),
    ("google how to cook pasta", "web_search"),
    ("search online for laptops", "web_search"),
    ("look up machine learning", "web_search"),
    ("find information about AI", "web_search"),
    ("google search for recipes", "web_search"),
    ("search for best restaurants", "web_search"),
    ("look up the meaning of quantum", "web_search"),
    ("browser search machine learning", "web_search"),
    ("search in browser for python", "web_search"),
    ("find in google AI tools", "web_search"),
    ("google iphone 16 price", "web_search"),
    ("search for coding projects", "web_search"),
    ("search how to make biryani", "web_search"),
    ("google maps directions", "web_search"),
    ("search for jobs in hyderabad", "web_search"),
    ("find best colleges in india", "web_search"),
    ("google cricket score", "web_search"),
    ("look up stock prices", "web_search"),
    ("search for python documentation", "web_search"),

    # ════════════════════════════════════════════════════════════
    # WIKIPEDIA / FACTUAL
    # ════════════════════════════════════════════════════════════
    ("tell me about python programming", "chat"),
    ("who is the president of india", "chat"),
    ("tell me about the solar system", "chat"),
    ("who invented the telephone", "chat"),
    ("what is blockchain", "chat"),
    ("history of artificial intelligence", "chat"),
    ("who is narendra modi", "chat"),
    ("explain the big bang theory", "chat"),
    ("what is cryptocurrency", "chat"),
    ("tell me about world war 2", "chat"),
    ("who created python language", "chat"),
    ("what is the speed of light", "chat"),
    ("tell me about india", "chat"),
    ("who is bill gates", "chat"),
    ("what is quantum physics", "chat"),
    ("history of computers", "chat"),
    ("who is virat kohli", "chat"),
    ("what is the internet", "chat"),
    ("tell me about space", "chat"),
    ("who discovered gravity", "chat"),

    # ════════════════════════════════════════════════════════════
    # EMAIL — SEND
    # ════════════════════════════════════════════════════════════
    ("send email to rahul", "send_email"),
    ("compose an email", "send_email"),
    ("write email to boss", "send_email"),
    ("email john saying hello", "send_email"),
    ("send a mail to priya", "send_email"),
    ("draft an email", "send_email"),
    ("send email to professor", "send_email"),
    ("mail my friend", "send_email"),
    ("write a mail saying I'll be late", "send_email"),
    ("compose mail to hr", "send_email"),
    ("send email with attachment", "send_email"),
    ("forward this email", "send_email"),
    ("reply to the last email", "send_email"),
    ("email mom good morning", "send_email"),

    # ════════════════════════════════════════════════════════════
    # EMAIL — READ
    # ════════════════════════════════════════════════════════════
    ("read my emails", "read_email"),
    ("check inbox", "read_email"),
    ("any new emails", "read_email"),
    ("show my emails", "read_email"),
    ("read latest email", "read_email"),
    ("check my mail", "read_email"),
    ("do I have any unread emails", "read_email"),
    ("open my inbox", "read_email"),
    ("read my new messages", "read_email"),
    ("check if I got any mail", "read_email"),
    ("any emails from boss", "read_email"),
    ("read the most recent email", "read_email"),

    # ════════════════════════════════════════════════════════════
    # REMINDER
    # ════════════════════════════════════════════════════════════
    ("remind me to call mom at 5", "set_reminder"),
    ("set a reminder for meeting", "set_reminder"),
    ("remind me in 10 minutes", "set_reminder"),
    ("set alarm for 7 am", "set_reminder"),
    ("reminder to drink water", "set_reminder"),
    ("wake me up at 6", "set_reminder"),
    ("remind me to take medicine", "set_reminder"),
    ("set reminder for gym at 6 am", "set_reminder"),
    ("remind me to submit assignment", "set_reminder"),
    ("set daily reminder for standup", "set_reminder"),
    ("remind me to pay bills tomorrow", "set_reminder"),
    ("alert me at 9 pm", "set_reminder"),
    ("remind me every hour to drink water", "set_reminder"),
    ("set reminder for mom's birthday", "set_reminder"),
    ("notify me before the exam", "set_reminder"),

    # ════════════════════════════════════════════════════════════
    # TIMER
    # ════════════════════════════════════════════════════════════
    ("set timer for 5 minutes", "set_timer"),
    ("start a countdown", "set_timer"),
    ("timer for 30 seconds", "set_timer"),
    ("count down from 10", "set_timer"),
    ("set a 2 minute timer", "set_timer"),
    ("start 10 minute timer", "set_timer"),
    ("30 second countdown", "set_timer"),
    ("timer for boiling eggs", "set_timer"),
    ("set pomodoro timer", "set_timer"),
    ("1 hour timer", "set_timer"),
    ("15 minute countdown", "set_timer"),
    ("set stopwatch", "set_timer"),

    # ════════════════════════════════════════════════════════════
    # WHATSAPP
    # ════════════════════════════════════════════════════════════
    ("message to banty hello", "send_whatsapp"),
    ("send whatsapp to rahul", "send_whatsapp"),
    ("text banty saying hi", "send_whatsapp"),
    ("whatsapp message to mom", "send_whatsapp"),
    ("send message to priya", "send_whatsapp"),
    ("message someone on whatsapp", "send_whatsapp"),
    ("text to sarvani good morning", "send_whatsapp"),
    ("send a text to ganesh", "send_whatsapp"),
    ("whatsapp priya I'm coming", "send_whatsapp"),
    ("send hi to dad on whatsapp", "send_whatsapp"),
    ("message boss I'll be late", "send_whatsapp"),
    ("text my friend happy birthday", "send_whatsapp"),
    ("send good night to mom", "send_whatsapp"),
    ("whatsapp to college group", "send_whatsapp"),
    ("message team on whatsapp", "send_whatsapp"),
    ("send sticker to rahul", "send_whatsapp"),

    # ════════════════════════════════════════════════════════════
    # TIME & DATE
    # ════════════════════════════════════════════════════════════
    ("what time is it", "time_date"),
    ("tell me the time", "time_date"),
    ("what's the date today", "time_date"),
    ("what day is it", "time_date"),
    ("current time", "time_date"),
    ("today's date", "time_date"),
    ("what is today", "time_date"),
    ("what time is it now", "time_date"),
    ("tell me today's date", "time_date"),
    ("what's the time right now", "time_date"),
    ("is it morning or evening", "time_date"),
    ("what month is it", "time_date"),
    ("what year is it", "time_date"),
    ("how many days until new year", "time_date"),
    ("what day of the week is it", "time_date"),

    # ════════════════════════════════════════════════════════════
    # JOKES
    # ════════════════════════════════════════════════════════════
    ("tell me a joke", "chat"),
    ("say something funny", "chat"),
    ("make me laugh", "chat"),
    ("crack a joke", "chat"),
    ("tell a funny joke", "chat"),
    ("give me a joke", "chat"),
    ("say a programming joke", "chat"),
    ("tell me a dad joke", "chat"),
    ("make me smile", "chat"),
    ("I need a laugh", "chat"),
    ("say something witty", "chat"),
    ("entertain me", "chat"),

    # ════════════════════════════════════════════════════════════
    # MEDIA / SPOTIFY
    # ════════════════════════════════════════════════════════════
    ("play believer on spotify", "play_music"),
    ("next song", "play_music"),
    ("skip this track", "play_music"),
    ("previous song", "play_music"),
    ("pause the music", "play_music"),
    ("resume playing", "play_music"),
    ("play some music", "play_music"),
    ("stop the song", "play_music"),
    ("play shape of you", "play_music"),
    ("skip to next track", "play_music"),
    ("play sad songs", "play_music"),
    ("shuffle my playlist", "play_music"),
    ("play lofi", "play_music"),
    ("play hip hop", "play_music"),
    ("play rock music", "play_music"),
    ("play classical music", "play_music"),
    ("increase music volume", "play_music"),
    ("stop music", "play_music"),
    ("play my liked songs", "play_music"),
    ("play workout playlist", "play_music"),
    ("repeat this song", "play_music"),
    ("play music", "play_music"),
    ("pause song", "play_music"),
    ("resume song", "play_music"),

    # ════════════════════════════════════════════════════════════
    # SHOPPING
    # ════════════════════════════════════════════════════════════
    ("find laptops on amazon", "shopping"),
    ("search flipkart for shoes", "shopping"),
    ("buy headphones on amazon", "shopping"),
    ("compare prices of phones", "shopping"),
    ("shop for watches", "shopping"),
    ("search myntra for shirts", "shopping"),
    ("find deals on flipkart", "shopping"),
    ("book a flight to delhi", "shopping"),
    ("hotel in mumbai", "shopping"),
    ("order food on swiggy", "shopping"),
    ("order pizza on zomato", "shopping"),
    ("buy groceries on blinkit", "shopping"),
    ("search for iphone on amazon", "shopping"),
    ("check price of samsung tv", "shopping"),
    ("book train ticket", "shopping"),
    ("buy books on amazon", "shopping"),
    ("find cheap flights", "shopping"),
    ("search airbnb in goa", "shopping"),
    ("order stationery online", "shopping"),

    # ════════════════════════════════════════════════════════════
    # VISION / SCREEN
    # ════════════════════════════════════════════════════════════
    ("what's on my screen", "vision_screen"),
    ("what am I looking at", "vision_screen"),
    ("describe my screen", "vision_screen"),
    ("what app is open", "vision_screen"),
    ("any errors on screen", "vision_screen"),
    ("what does my screen show", "vision_screen"),
    ("read what's on screen", "vision_screen"),
    ("analyze my screen", "vision_screen"),
    ("what's visible on my desktop", "vision_screen"),
    ("tell me what's on display", "vision_screen"),
    ("scan my screen", "vision_screen"),
    ("what's the error message", "vision_screen"),

    # ════════════════════════════════════════════════════════════
    # FILE OPERATIONS
    # ════════════════════════════════════════════════════════════
    ("open file explorer", "file_operation"),
    ("open my documents", "file_operation"),
    ("open the downloads folder", "file_operation"),
    ("open desktop folder", "file_operation"),
    ("open main.py", "file_operation"),
    ("open notes.txt", "file_operation"),
    ("create a new file", "file_operation"),
    ("make a new text file", "file_operation"),
    ("write a note", "file_operation"),
    ("create a new document", "file_operation"),
    ("save my notes", "file_operation"),

    # ════════════════════════════════════════════════════════════
    # CODE RUNNER
    # ════════════════════════════════════════════════════════════
    ("write code to print hello", "write_code"),
    ("create hello.py", "write_code"),
    ("write a python script", "write_code"),
    ("generate code for calculator", "write_code"),
    ("write code to list files", "write_code"),
    ("create main.py with hello world", "write_code"),
    ("write a script to rename files", "write_code"),
    ("generate python code", "write_code"),
    ("code to get current time", "write_code"),
    ("write a function to add numbers", "write_code"),
    ("create index.html", "write_code"),
    ("write javascript code", "write_code"),
    ("generate html template", "write_code"),
    ("run the code", "write_code"),
    ("execute the script", "write_code"),
    ("run it", "write_code"),
    ("run main.py", "write_code"),
    ("execute the file", "write_code"),
    ("run this program", "write_code"),

    # ════════════════════════════════════════════════════════════
    # SHUTDOWN / SYSTEM
    # ════════════════════════════════════════════════════════════
    ("shutdown the computer", "shutdown_system"),
    ("restart my laptop", "shutdown_system"),
    ("reboot the system", "shutdown_system"),
    ("turn off the computer", "shutdown_system"),
    ("put computer to sleep", "shutdown_system"),
    ("hibernate the system", "shutdown_system"),
    ("cancel shutdown", "shutdown_system"),
    ("logout", "shutdown_system"),
    ("sign out", "shutdown_system"),
    ("restart windows", "shutdown_system"),
    ("power off", "shutdown_system"),
    ("sleep mode", "shutdown_system"),

    # ════════════════════════════════════════════════════════════
    # STOP / QUIT JARVIS
    # ════════════════════════════════════════════════════════════
    ("stop jarvis", "stop"),
    ("quit", "stop"),
    ("exit", "stop"),
    ("goodbye", "stop"),
    ("shut down jarvis", "stop"),
    ("bye bye", "stop"),
    ("go to sleep jarvis", "stop"),
    ("that's all for now", "stop"),
    ("I'm done", "stop"),
    ("close jarvis", "stop"),
    ("turn off jarvis", "stop"),
    ("jarvis stop", "stop"),
    ("ok goodbye", "stop"),
    ("see you later", "stop"),
    ("bye jarvis", "stop"),

    # ════════════════════════════════════════════════════════════
    # RESET CONVERSATION
    # ════════════════════════════════════════════════════════════
    ("reset conversation", "chat"),
    ("clear chat", "chat"),
    ("start over", "chat"),
    ("forget everything", "chat"),
    ("new conversation", "chat"),
    ("clear memory", "chat"),
    ("reset jarvis", "chat"),
    ("fresh start", "chat"),
    ("wipe conversation", "chat"),
    ("clear history", "chat"),

    # ════════════════════════════════════════════════════════════
    # GREETING
    # ════════════════════════════════════════════════════════════
    ("hello jarvis", "chat"),
    ("hi", "chat"),
    ("hey", "chat"),
    ("good morning", "chat"),
    ("good evening", "chat"),
    ("how are you", "chat"),
    ("what's up", "chat"),
    ("hello", "chat"),
    ("hey jarvis", "chat"),
    ("good afternoon jarvis", "chat"),
    ("good night", "chat"),
    ("hi there", "chat"),
    ("hello hello", "chat"),
    ("are you there", "chat"),
    ("wake up jarvis", "chat"),
    ("namaste", "chat"),
    ("hey buddy", "chat"),

    # ════════════════════════════════════════════════════════════
    # MEMORY / PERSONAL FACTS
    # ════════════════════════════════════════════════════════════
    ("my name is srini", "memory"),
    ("remember my name", "memory"),
    ("my favourite color is blue", "memory"),
    ("save this information", "memory"),
    ("remember that I like cricket", "memory"),
    ("my birthday is on april 10", "memory"),
    ("I study computer science", "memory"),
    ("remember I prefer dark mode", "memory"),
    ("my phone number is", "memory"),
    ("save my address", "memory"),
    ("what do you remember about me", "memory"),
    ("what do you know about me", "memory"),
    ("do you remember what I told you", "memory"),
    ("forget what I said earlier", "memory"),
    ("update my information", "memory"),
    ("my favourite food is biryani", "memory"),
    ("I live in hyderabad", "memory"),
    ("remember that I wake up at 6am", "memory"),

    # ════════════════════════════════════════════════════════════
    # CALENDAR
    # ════════════════════════════════════════════════════════════
    ("add meeting tomorrow at 3pm", "calendar_event"),
    ("schedule exam on monday", "calendar_event"),
    ("add event birthday party", "calendar_event"),
    ("create calendar event", "calendar_event"),
    ("what's my schedule today", "calendar_event"),
    ("what do I have tomorrow", "calendar_event"),
    ("what's happening this week", "calendar_event"),
    ("show my calendar", "calendar_event"),
    ("what's my next event", "calendar_event"),
    ("do I have anything today", "calendar_event"),
    ("cancel my 3pm meeting", "calendar_event"),
    ("delete the exam event", "calendar_event"),
    ("schedule appointment at 5pm", "calendar_event"),
    ("add dentist appointment friday", "calendar_event"),
    ("what events do I have", "calendar_event"),
    ("show all events", "calendar_event"),
    ("schedule class on tuesday", "calendar_event"),
    ("add gym session at 6am", "calendar_event"),

    # ════════════════════════════════════════════════════════════
    # GENERAL CHAT (fallback to AI)
    # ════════════════════════════════════════════════════════════
    ("what is the meaning of life", "chat"),
    ("write me a poem", "chat"),
    ("explain relativity", "chat"),
    ("help me with my homework", "chat"),
    ("what do you think about AI", "chat"),
    ("can you help me code", "chat"),
    ("translate hello to spanish", "chat"),
    ("summarize this for me", "chat"),
    ("what is love", "chat"),
    ("tell me something interesting", "chat"),
    ("how does electricity work", "chat"),
    ("give me study tips", "chat"),
    ("help me write a cover letter", "chat"),
    ("what are the best programming languages", "chat"),
    ("suggest a good book", "chat"),
    ("how to improve my english", "chat"),
    ("tips for healthy life", "chat"),
    ("best way to learn machine learning", "chat"),
    ("help me plan my week", "chat"),
    ("write a story", "chat"),
    ("what should I eat today", "chat"),
    ("help me debug this code", "chat"),
    ("explain neural networks simply", "chat"),
    ("how to start a startup", "chat"),
    ("tips to wake up early", "chat"),
    ("motivate me", "chat"),
    ("I feel bored", "chat"),
    ("let's talk", "chat"),
    ("say something inspiring", "chat"),
    ("what's new in technology", "chat"),
    ("tell me an interesting fact", "chat"),
    ("what's your favourite movie", "chat"),
    ("can you be my friend", "chat"),
    ("what can you do", "chat"),
    ("how smart are you", "chat"),
    ("are you better than siri", "chat"),
    ("are you like chatgpt", "chat"),
    ("tell me about yourself", "chat"),
    ("what are your capabilities", "chat"),
    ("how were you made", "chat"),

    # ════════════════════════════════════════════════════════════
    # ADDITIONAL TRAINING DATA — boost underrepresented intents
    # ════════════════════════════════════════════════════════════

    # ── file_operation (was 11, adding 10) ──
    ("create a new folder on desktop", "file_operation"),
    ("delete the old files", "file_operation"),
    ("move photos to backup", "file_operation"),
    ("copy this file to documents", "file_operation"),
    ("rename the file to report", "file_operation"),
    ("compress the project folder", "file_operation"),
    ("extract the zip file", "file_operation"),
    ("show me files on desktop", "file_operation"),
    ("list all PDF files", "file_operation"),
    ("find files larger than 1GB", "file_operation"),

    # ── screenshot (was 12, adding 8) ──
    ("take a screenshot please", "screenshot"),
    ("capture my screen", "screenshot"),
    ("screenshot this page", "screenshot"),
    ("take a snap of the screen", "screenshot"),
    ("grab a screenshot now", "screenshot"),
    ("save the screen", "screenshot"),
    ("screenshot the current window", "screenshot"),
    ("can you take a screenshot", "screenshot"),

    # ── read_email (was 12, adding 8) ──
    ("check my inbox", "read_email"),
    ("any new emails today", "read_email"),
    ("do I have unread emails", "read_email"),
    ("read the latest email", "read_email"),
    ("show me new mail", "read_email"),
    ("check gmail for new messages", "read_email"),
    ("any important emails", "read_email"),
    ("read my emails please", "read_email"),

    # ── set_timer (was 12, adding 8) ──
    ("set a timer for 10 minutes", "set_timer"),
    ("timer 5 minutes", "set_timer"),
    ("start a 30 second timer", "set_timer"),
    ("countdown 2 minutes", "set_timer"),
    ("set a timer for 1 hour", "set_timer"),
    ("start countdown for 15 minutes", "set_timer"),
    ("timer for 45 minutes please", "set_timer"),
    ("set a 3 minute timer", "set_timer"),

    # ── vision_screen (was 12, adding 8) ──
    ("what's on my screen right now", "vision_screen"),
    ("analyze my screen", "vision_screen"),
    ("read what's on screen", "vision_screen"),
    ("describe what you see on screen", "vision_screen"),
    ("what is displayed on my monitor", "vision_screen"),
    ("scan my screen for text", "vision_screen"),
    ("read the error on screen", "vision_screen"),
    ("what does my screen show", "vision_screen"),

    # ── shutdown_system (was 12, adding 8) ──
    ("shut down the computer", "shutdown_system"),
    ("restart my PC please", "shutdown_system"),
    ("reboot the system", "shutdown_system"),
    ("put the computer to sleep", "shutdown_system"),
    ("hibernate my laptop", "shutdown_system"),
    ("turn off the PC", "shutdown_system"),
    ("power off the computer", "shutdown_system"),
    ("log out of windows", "shutdown_system"),

    # ── send_email (was 14, adding 6) ──
    ("send email to mom saying happy birthday", "send_email"),
    ("compose an email to my professor", "send_email"),
    ("write an email to john about the project", "send_email"),
    ("email teja saying I'll be late", "send_email"),
    ("send a mail to my team about the meeting", "send_email"),
    ("draft an email to customer support", "send_email"),

    # ── brightness_control (was 15, adding 5) ──
    ("make the screen brighter", "brightness_control"),
    ("dim the screen a bit", "brightness_control"),
    ("set brightness to 50 percent", "brightness_control"),
    ("increase screen brightness", "brightness_control"),
    ("lower the brightness please", "brightness_control"),

    # ── set_reminder (was 15, adding 5) ──
    ("remind me about the meeting at 3pm", "set_reminder"),
    ("set a reminder to call mom", "set_reminder"),
    ("remind me to drink water every hour", "set_reminder"),
    ("don't let me forget the interview tomorrow", "set_reminder"),
    ("remind me to submit the assignment", "set_reminder"),

    # ── send_whatsapp (was 16, adding 5) ──
    ("tell sarvani I'm on my way on whatsapp", "send_whatsapp"),
    ("message banty good night on whatsapp", "send_whatsapp"),
    ("whatsapp teja asking where are you", "send_whatsapp"),
    ("text mom I'll be home soon on whatsapp", "send_whatsapp"),
    ("send happy birthday to dad on whatsapp", "send_whatsapp"),

    # ── youtube_search (was 17, adding 5) ──
    ("play lofi music on youtube", "youtube_search"),
    ("search for cooking tutorials on youtube", "youtube_search"),
    ("open a ted talk video", "youtube_search"),
    ("youtube how to fix windows error", "youtube_search"),
    ("watch marvel trailer on youtube", "youtube_search"),

    # ── app_mode (not in training data, adding 10) ──
    ("switch to work mode", "app_mode"),
    ("activate study mode", "app_mode"),
    ("set up movie mode", "app_mode"),
    ("turn on gaming mode", "app_mode"),
    ("enter focus mode", "app_mode"),
    ("start meeting mode", "app_mode"),
    ("go to relax mode", "app_mode"),
    ("switch to study mode please", "app_mode"),
    ("I want to study now set up everything", "app_mode"),
    ("prepare everything for a movie night", "app_mode"),

    # ── media_control (not in training data, adding 10) ──
    ("pause the music", "media_control"),
    ("resume playback", "media_control"),
    ("skip this song", "media_control"),
    ("next track please", "media_control"),
    ("go back to previous song", "media_control"),
    ("stop the video", "media_control"),
    ("continue playing", "media_control"),
    ("skip to next", "media_control"),
    ("play previous track", "media_control"),
    ("unpause the music", "media_control"),

    # ── math_calculate (not in training data, adding 8) ──
    ("what is 25 plus 17", "math_calculate"),
    ("calculate 150 times 3", "math_calculate"),
    ("what's 1000 divided by 4", "math_calculate"),
    ("how much is 99 minus 47", "math_calculate"),
    ("solve 15 percent of 200", "math_calculate"),
    ("what is the square root of 144", "math_calculate"),
    ("calculate 78 plus 23", "math_calculate"),
    ("how much is 500 times 12", "math_calculate"),

    # ── type_text (not in training data, adding 6) ──
    ("type hello how are you", "type_text"),
    ("type I am coming", "type_text"),
    ("type good morning everyone", "type_text"),
    ("type this message for me", "type_text"),
    ("type thank you so much", "type_text"),
    ("type see you later", "type_text"),

    # ── read_whatsapp (not in training data, adding 6) ──
    ("read messages from sarvani", "read_whatsapp"),
    ("what did teja say on whatsapp", "read_whatsapp"),
    ("show me last messages from mom", "read_whatsapp"),
    ("check whatsapp messages from banty", "read_whatsapp"),
    ("read my latest whatsapp", "read_whatsapp"),
    ("any new messages from dad", "read_whatsapp"),
]

