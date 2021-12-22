import discord

realms = {
    # Air Nomads
    "Eastern Air Temple": {
        "desc": "The Eastern Air Temple was one of the two temples exclusively housing female airbenders. "
                "Like the other temples, its population was completely exterminated during the Air Nomad Genocide. "
                "Guru Pathik resided here for a considerable amount of time, "
                "as he waited years for Aang to come so he could teach the Avatar "
                "how to properly control the Avatar State.",
        "color": discord.Color.from_rgb(255, 255, 255),
        "img": "https://static.wikia.nocookie.net/avatar/images/b/b2/Eastern_Air_Temple.png/revision/latest?cb=20130705194029"
    },
    "Northern Air Temple": {
        "desc": "The Northern Air Temple is a temple that hosted only male monks. "
                "It is located in the upper reaches of the northern Earth Kingdom, "
                "built upon a snow-capped mountain. This temple was also a victim of the "
                "Air Nomad Genocide, along with all the other air temples. By 100 AG, "
                "it had become renowned for its arbitrary colonization by Earth Kingdom refugees, "
                "who were led by the mechanist. Up to that point, the area had undergone rapid "
                "industrialization.",
        "color": discord.Color.from_rgb(255, 255, 255),
        "img": "https://static.wikia.nocookie.net/avatar/images/3/3c/Northern_Air_Temple_in_171_AG.png/revision/latest/scale-to-width-down/500?cb=20151115113702"
    },
    "Southern Air Temple": {
        "desc": "The Southern Air Temple was one of the four sanctuaries owned by the Air Nomads. "
                "It is the one located closest to the Southern Water Tribe and exclusively housed "
                "male airbenders. This region is notable for being the childhood home of Avatar Aang, "
                "and it was also the place where Avatar Roku learned airbending.",
        "color": discord.Color.from_rgb(255, 255, 255),
        "img": "https://static.wikia.nocookie.net/avatar/images/3/33/Southern_Air_Temple_outlook.png/revision/latest/scale-to-width-down/200?cb=20140103181304"
    },
    "Western Air Temple": {
        "desc": "The Western Air Temple was a counterpart of the Eastern Air Temple, "
                "maintaining only female airbenders. It is situated in an island mountain range "
                "due north of the Fire Nation. Unlike the other air temples, "
                "this one consists of multiple small structures and portions versus "
                "merely a single large one. It too was a victim of the Air Nomad Genocide, "
                "which decimated all of its population. The temple is also notable in that, "
                "contrary to the other three temples, it is situated underneath the edge of a cliff, "
                "as opposed to a mountaintop. The spires seem as though they were constructed upside-down, "
                "and because of that, the temple is generally difficult to locate for passers-by.",
        "color": discord.Color.from_rgb(255, 255, 255),
        "img": "https://static.wikia.nocookie.net/avatar/images/3/37/Western_Air_Temple.png/revision/latest/scale-to-width-down/200?cb=20140821204332"
    },
    # Water Tribe
    "Foggy Swamp": {
        "desc": "Though an outlying expanse of the tribe, this vast and mysterious wetland occupies a "
                "considerable portion of the southwestern Earth Kingdom. It provides an ideal residence "
                "for the Foggy Swamp Tribe, who are descended from immigrants of the Southern Water Tribe. "
                "The Swamp has an extensive array of fauna and flora, the latter of which are actually "
                "just a series of roots connected to one central tree, the towering banyan grove.",
        "color": discord.Color.from_rgb(0, 196, 245),
        "img": "https://static.wikia.nocookie.net/avatar/images/6/68/Foggy_Swamp.png/revision/latest/scale-to-width-down/666?cb=20130630224556"
    },
    "Northern Water Tribe": {
        "desc": "The Northern Water Tribe is the largest division of its nation and is located on "
                "an island situated near the North Pole. The capital city, Agna Qel'a, prospers in "
                "its isolation. No attack from the Fire Nation on the city during the Hundred Year "
                "War ever ended in a loss for the tribe, including the tumultuous Siege of the North. "
                "After the fall of Ba Sing Se, the Northern Water Tribe boasted the only major city in "
                "the world to not be under Fire Nation jurisdiction.",
        "color": discord.Color.from_rgb(0, 196, 245),
        "img": "https://static.wikia.nocookie.net/avatar/images/6/63/Northern_Water_Tribe_entrance.png/revision/latest/scale-to-width-down/200?cb=20140122221731"
    },
    "Southern Water Tribe": {
        "desc": "The Southern Water Tribe is a minor division of the Water Tribe. "
                "Its people are scattered in tiny villages and settlements located on an island "
                "by the South Pole. Unlike its thriving sister tribe, the people of the Southern "
                "Water Tribe were teetering on the edge of extinction during the Hundred Year War due "
                "to Fire Nation raids. However, following the Siege of the North, several volunteers "
                "traveled from the Northern Water Tribe to help rebuild their sister tribe. "
                "Through their efforts, the South underwent a major expansion, and by 171 AG, "
                "it had a large harbor city as its capital, along with numerous other smaller cities "
                "and villages scattered around the South Pole.",
        "color": discord.Color.from_rgb(0, 196, 245),
        "img": "https://static.wikia.nocookie.net/avatar/images/e/e1/Southern_Water_Tribe_capital_city.png/revision/latest/scale-to-width-down/700?cb=20130918004521"
    },
    # Earth Kingdom
    # Central Regions
    # "Full Moon Bay": {
    #     "desc": "Full Moon Bay is a secluded cove in East Lake, located just south of Ba Sing Se. "
    #             "It is the location of a hidden ferry station that refugees from all over the southern "
    #             "portion of the Earth Kingdom come to on their way to Ba Sing Se.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/7/71/Earth_Kingdom_ferries.png/revision/latest/scale-to-width-down/666?cb=20140413233808"
    # },
    # "Great Divide": {
    #     "desc": "The Great Divide is the largest canyon in the world. "
    #             "It is located in the rocky regions of the central Earth Kingdom.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/f/f8/Great_Divide.png/revision/latest/scale-to-width-down/699?cb=20131202200442"
    # },
    # "Si Wong Desert": {
    #     "desc": "The Si Wong Desert is the largest desert in the world. "
    #             "It is almost impossible to successfully navigate. "
    #             "It is sparsely inhabited by Si Wong tribes.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/4/46/Si_Wong_Desert.png/revision/latest/scale-to-width-down/200?cb=20140407161000"
    # },
    # # Northeastern regions
    # "Ba Sing Se": {
    #     "desc": "Ba Sing Se is the monolithic capital of the Earth Kingdom, "
    #             "encompassing nearly the entire northeast corner of the country. "
    #             "It was the last great Earth Kingdom stronghold after the fall of Omashu. "
    #             "Ba Sing Se means 'impenetrable city', an honorary reference to its two "
    #             "insurmountable walls, the gates of which have no hinges and can therefore not "
    #             "be opened in any way aside from the use of earthbending.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/6/6f/Ba_Sing_Se.png/revision/latest/scale-to-width-down/200?cb=20140422090139"
    # },
    # "Serpent's Pass": {
    #     "desc": "The Serpent's Pass is a narrow strip of land between the East and West Lakes that "
    #             "links the southern and northern halves of the Earth Kingdom. It is one of the very "
    #             "few direct paths to the capital, Ba Sing Se. The pathway is named after the serpent "
    #             "which guards the point at which the East and West Lakes meet. Here, the Serpent's Pass "
    #             "dips below the lakes for a limited distance. These adversities make the Serpent's Pass "
    #             "a typically avoided entryway into Ba Sing Se, and most refugees prefer to go by ferry "
    #             "instead.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/f/ff/East_and_West_Lakes.png/revision/latest/scale-to-width-down/666?cb=20140413233808"
    # },
    # # Northwestern regions
    # "Merchant town": {
    #     "desc": "The merchant town is a minor trading settlement located high in the mountains of the "
    #             "northwestern Earth Kingdom. Historically, this region was the site of numerous airbender "
    #             "murders, as survivors of the genocide were tricked by firebenders into coming to this "
    #             "location when they heard rumors of its mysterious possession of Air Nomad relics. "
    #             "Such airbenders were consequently killed in a decisive ambush.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/8/86/Merchant_town.png/revision/latest/scale-to-width-down/700?cb=20200421094436"
    # },
    # # Southern regions
    # "Chin Village": {
    #     "desc": "Chin Village is a small town located on the cliffs of the Earth Kingdom's "
    #             "southwestern coast. It is named for Chin the Great, a warlord and conqueror "
    #             "who nearly conquered the Earth Kingdom. It plays host to the unique 'Avatar Day' "
    #             "festival, a celebration that used to be a celebration in hate of the Avatar but is "
    #             "now held in honor of the Avatar.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/8/8e/Chin_Village_center.png/revision/latest/scale-to-width-down/200?cb=20140215111851"
    # },
    # "Gaoling": {
    #     "desc": "Gaoling is a large town located within a mountain range in the southern Earth Kingdom. "
    #             "It is home to both the wealthy Beifong family and the Earth Rumble tournaments. "
    #             "An old, well-established city, Gaoling has a spectrum of people residing in it, "
    #             "ranging from the very rich to the very poor. Because it was not in a particularly "
    #             "strategic location, the town was left untouched by the Hundred Year War. "
    #             "This is evidenced by the attitude of many of its residents.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/f/f5/Gaoling.png/revision/latest/scale-to-width-down/700?cb=20140317210010"
    # },
    # "Kyoshi Island": {
    #     "desc": "Kyoshi Island is a small island off the southern coast of the Earth Kingdom, "
    #             "dotted with many small villages. It is famous as the birthplace of Avatar Kyoshi, "
    #             "and as the home of the elite Kyoshi Warriors.[20] The island was created when Chin "
    #             "the Conqueror threatened to invade and conquer the former peninsula. "
    #             "Avatar Kyoshi separated Yokoya Peninsula from the Earth Kingdom mainland to keep her "
    #             "people safe from future threats.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/e/e3/Kyoshi_Island.png/revision/latest/scale-to-width-down/666?cb=20130819084150"
    # },
    # "Omashu": {
    #     "desc": "Omashu is the second largest city in the Earth Kingdom and the capital of one of its "
    #             "provinces. Only Ba Sing Se, the titanic capital of the Earth Kingdom, is larger. "
    #             "It was one of the last great strongholds of the Earth Kingdom before its fall in the "
    #             "months before the end of the Hundred Year War, and a supplier of men and weaponry. "
    #             "Previously ruled by King Bumi, Omashu was taken over by the Fire Nation and renamed "
    #             "New Ozai. During the Day of Black Sun, King Bumi single-handedly liberated Omashu, "
    #             "and all the powerless firebenders abandoned the city.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/c/cc/Omashu.png/revision/latest/scale-to-width-down/200?cb=20140106134023"
    # },
    # "Plains village": {
    #     "desc": "The plains village is located in the arid grasslands of the southern Earth Kingdom, "
    #             "to the west of the Si Wong Desert. It was not the most ideal place to live in and was home "
    #             "to several suspicious characters, including Gow, who, along with his gang of thugs, passed "
    #             "off as Earth Kingdom soldiers in order to force the citizens to yield to their will. "
    #             "They often forcefully enlisted unwilling citizens into the Earth Kingdom Army and stole "
    #             "from those they considered weak, and as such, the town was often forced to live in fear "
    #             "of this band. The citizens of the village seemed to harbor a severe hatred for the Fire Nation, "
    #             "and several of its citizens left to fight in the Hundred Year War.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/2/25/Plains_village.png/revision/latest/scale-to-width-down/666?cb=20140331143653"
    # },
    # "Zaofu": {
    #     "desc": "Zaofu is an autonomous city-state, located in the southwestern part of the "
    #             "Earth Kingdom, and the home of the Metal Clan. Founded by Suyin Beifong, "
    #             "the Clan's matriarch, Zaofu is constructed entirely out of metal and is regarded by "
    #             "some as the safest city in the world. It was annexed by the Earth Empire temporarily "
    #             "in 174 AG, but power over the city was returned to Suyin following Kuvira's surrender.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/3/35/Zaofu.png/revision/latest/scale-to-width-down/700?cb=20140726200554"
    # },
    # # Western regions
    # "Cave of Two Lovers": {
    #     "desc": "SEEECRET TUNNELLLLLLLLLLLLL...\n"
    #             "Located near the city of Omashu in the Earth Kingdom, the Cave of Two Lovers is a "
    #             "secret tunnel that passes through a section of the Kolau Mountain Range. "
    #             "The tunnel is actually a giant underground labyrinth full of dangerous animals "
    #             "including wolfbats and badgermoles.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/7/72/Cave_of_Two_Lovers.png/revision/latest/scale-to-width-down/200?cb=20140128105157"
    # },
    # "Farming Village": {
    #     "desc": "This farming village is a small village located in the western Earth Kingdom. "
    #             "Zuko and Iroh traveled to the village so Iroh could receive treatment for a rash "
    #             "caused by the white jade plant.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/6/69/Farming_village.png/revision/latest/scale-to-width-down/666?cb=20140128105158"
    # },
    # "Gaipan": {
    #     "desc": "Gaipan is a small village located in the central Earth Kingdom. "
    #             "After being overtaken by the Fire Nation, it was evacuated shortly "
    #             "before being destroyed by a catastrophic flood.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/7/77/Gaipan.png/revision/latest/scale-to-width-down/666?cb=20120526073606"
    # },
    # "Mining village": {
    #     "desc": "The mining village is a medium-sized village located in the Earth Kingdom. "
    #             "It is located on the northwestern coast of the Earth Kingdom, "
    #             "and its inhabitants make a living by mining coal in several nearby mines.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/5/5f/Mining_village.png/revision/latest/scale-to-width-down/500?cb=20140108094313"
    # },
    # "River village": {
    #     "desc": "The river village is located in the western Earth Kingdom, "
    #             "situated between the forks of a large river. It serves as a "
    #             "regional trading hub and ideal location for merchants to sell their wares.",
    #     "color": discord.Color.from_rgb(12, 148, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/1/11/River_village.png/revision/latest/scale-to-width-down/666?cb=20130630170828"
    # },
    # # Fire nation
    # "Boiling Rock": {
    #     "desc": "The Boiling Rock is a massive Fire Nation prison. Its name is derived from the "
    #             "fact that the prison is on an island in the middle of a boiling lake on a volcanic "
    #             "island. The Boiling Rock is where the most dangerous prisoners in the Fire Nation are "
    #             "held, domestic and foreign alike.",
    #     "color": discord.Color.from_rgb(112, 0, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/3/32/Boiling_Rock.png/revision/latest/scale-to-width-down/666?cb=20110119230313"
    # },
    # "Ember Island": {
    #     "desc": "Ember Island is a small resort located in the outer islands of the Fire Nation. "
    #             "It is home to many luxurious resorts and vacation homes for the wealthy and powerful. "
    #             "The beaches are among the most popular in the country and host many popular kuai ball "
    #             "games.",
    #     "color": discord.Color.from_rgb(112, 0, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/4/45/Ember_Island_beach.png/revision/latest/scale-to-width-down/666?cb=20140908141112"
    # },
    # "Fire Fountain City": {
    #     "desc": "Fire Fountain City is a large, industrial city located in the Fire Nation. "
    #             "It is named for the large, fire-breathing statue of Fire Lord Ozai in its center. "
    #             "It is located on one of the many islands in the eastern half of the Fire Nation.",
    #     "color": discord.Color.from_rgb(112, 0, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/1/15/Fire_Fountain_City.png/revision/latest/scale-to-width-down/666?cb=20101227195930"
    # },
    # "Fire Nation Capital": {
    #     "desc": "The Fire Nation Capital is the seat of the government for the Fire Nation. "
    #             "It is home to the Fire Lord, the royal family, and nobles of the Fire Nation. "
    #             "The capital is located on the Capital Island, a larger island in the western region "
    #             "of the Fire Nation.",
    #     "color": discord.Color.from_rgb(112, 0, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/7/7e/Capital_harbor.png/revision/latest/scale-to-width-down/200?cb=20090312231634"
    # },
    # "Hira'a village": {
    #     "desc": "The village of Hira'a is a small settlement surrounded by mountains and lush "
    #             "forests and situated relatively close to the Forgetful Valley.",
    #     "color": discord.Color.from_rgb(112, 0, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/4/45/Hira%27a.png/revision/latest?cb=20130323190706&path-prefix=es"
    # },
    # "Jang Hui": {
    #     "desc": "Jang Hui is a small, poor village located in the outer islands of the Fire Nation. "
    #             "Located on the Jang Hui River, this unique Fire Nation village is made up of floating "
    #             "houseboats connected together.",
    #     "color": discord.Color.from_rgb(112, 0, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/4/40/Jang_Hui.png/revision/latest/scale-to-width-down/666?cb=20140613143541"
    # },
    # "Shu Jing": {
    #     "desc": "Shu Jing is a town located in the Fire Nation. Situated on a cliff above a river "
    #             "and waterfalls and surrounded by beautiful mountains, this is one of the many small, "
    #             "peaceful villages that are tucked away throughout the Fire Nation islands.",
    #     "color": discord.Color.from_rgb(112, 0, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/b/ba/Shu_Jing.png/revision/latest/scale-to-width-down/666?cb=20140905234216"
    # },
    # "Sun Warriors' ancient city": {
    #     "desc": "This location is a sprawling, ancient city that was thought to be an uninhabited ruin. "
    #             "Aang and Zuko discovered that the Sun Warrior civilization still existed here.",
    #     "color": discord.Color.from_rgb(112, 0, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/3/33/Sun_Warriors%27_ancient_city.png/revision/latest/scale-to-width-down/200?cb=20111111174035"
    # },
    # "Yon Rha's village": {
    #     "desc": "Yon Rha's village is a minor settlement located in a hilly region of the southern Fire Nation.",
    #     "color": discord.Color.from_rgb(112, 0, 0),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/e/e7/Yon_Rha%27s_village.png/revision/latest/scale-to-width-down/666?cb=20121228073945"
    # },
    # # United Republic of Nations
    # "Harbor town": {
    #     "desc": "The harbor town is a small coastal settlement located in the southern United Republic "
    #             "of Nations. Despite its strategic location, the village managed to stay free from "
    #             "Fire Nation occupation during the Hundred Year War.",
    #     "color": discord.Color.from_rgb(222, 166, 24),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/c/c1/Harbor_town.png/revision/latest/scale-to-width-down/666?cb=20130714134743"
    # },
    # "Makapu Village": {
    #     "desc": "Makapu Village is a small farming town located in the northeastern United Republic "
    #             "of Nations on the slopes of Mt. Makapu, an active volcano. "
    #             "Volcanic eruptions have caused the soil around the volcano to become rich in minerals, "
    #             "making it perfect for agriculture. It was notable for being the residence of the "
    #             "fortuneteller Aunt Wu. The village is also home to the rare panda lily flower, "
    #             "which grows in and around the crater of the volcano, and which is commonly used "
    #             "as a symbol of everlasting love and unity.",
    #     "color": discord.Color.from_rgb(222, 166, 24),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/e/e2/Makapu_Village.png/revision/latest/scale-to-width-down/200?cb=20130814112420"
    # },
    # "Republic City": {
    #     "desc": "Republic City is a large metropolis located in the lower areas of a mountainous region, "
    #             "with large bodies of water in the immediate vicinity. It was founded as the capital "
    #             "of the United Republic of Nations, a fifth nation created by Fire Lord Zuko and Avatar "
    #             "Aang after the end of the Hundred Year War.",
    #     "color": discord.Color.from_rgb(222, 166, 24),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/a/a9/Republic_City_skyline.png/revision/latest/scale-to-width-down/200?cb=20121112152518"
    # },
    # "Seedy merchants pier": {
    #     "desc": "The seedy merchants pier is a small harbor and town in the southern "
    #             "United Republic of Nations. It is a tiny trading port with a seedy element. "
    #             "Here one can buy almost anything, from jewelry to pottery to musical instruments "
    #             "and trivial items. The seedy merchant's pier welcomes all nations so long as they "
    #             "have an inclination for a bargain.",
    #     "color": discord.Color.from_rgb(222, 166, 24),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/9/94/Seedy_merchants_pier.png/revision/latest/scale-to-width-down/200?cb=20140112230441"
    # },
    # "Senlin Village": {
    #     "desc": "Senlin Village is a small farming settlement located within the scorched forest in the "
    #             "southern United Republic of Nations. The surrounding woodland is protected by a typically "
    #             "peaceful, though occasionally enraged, spirit known as Hei Bai. Due to a lack of strategical "
    #             "advantage, the Fire Nation did not occupy this former Earth Kingdom village during the Hundred "
    #             "Year War. The prevailing occupation of the settlement's inhabitants are farming and trading, "
    #             "though some villagers joined the Earth Kingdom Army during the War.",
    #     "color": discord.Color.from_rgb(222, 166, 24),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/6/63/Senlin.png/revision/latest/scale-to-width-down/666?cb=20130620103404"
    # },
    # "Taku": {
    #     "desc": "Taku is an abandoned city located on the shores of the United Republic of Nations, "
    #             "formerly the northwestern Earth Kingdom. Prior to the Hundred Year War, the city was an "
    #             "important center of commerce. However, it was destroyed by the Fire Nation during the "
    #             "first wave of attacks due to its strategic location and importance to the Earth Kingdom. "
    #             "All that remains now are ruins.",
    #     "color": discord.Color.from_rgb(222, 166, 24),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/7/73/Taku.png/revision/latest/scale-to-width-down/666?cb=20140113133942"
    # },
    # "Yu Dao": {
    #     "desc": "Yu Dao was once an Earth Kingdom city that was established as the first of the "
    #             "Fire Nation colonies. It was located in a wide, flat valley which was bounded by "
    #             "rocky terrain on all sides. The city was enclosed by a sandstone wall with one opening "
    #             "which served as the gateway to the city. Yu Dao's streets were lined by predominantly "
    #             "low rise buildings which were built in a unique style that combined Earth Kingdom and "
    #             "Fire Nation architecture.",
    #     "color": discord.Color.from_rgb(222, 166, 24),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/d/da/Overview_of_Yu_Dao.png/revision/latest/scale-to-width-down/700?cb=20200810231731"
    # },
    # "Air Temple Island": {
    #     "desc": "Air Temple Island is a small isle located off the coast of Republic City in Yue Bay. "
    #             "The island is formally independent of the nearby United Republic, "
    #             "and is under the sole jurisdiction of the new Air Nation. Comprised of several structures, "
    #             "the temple was built by Avatar Aang himself and is home to Tenzin, his wife Pema, "
    #             "and their four children Jinora, Ikki, Meelo, and Rohan, as well as the Air Acolytes. "
    #             "Also residing on the island are colonies of flying bison and ring-tailed winged lemurs.",
    #     "color": discord.Color.from_rgb(222, 166, 24),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/8/8d/Air_Temple_Island_overview.png/revision/latest/scale-to-width-down/700?cb=20121107105550"
    # },
    # # Neutral locations
    # "Mo Ce Sea": {
    #     "desc": "The Mo Ce Sea is an open body of water located between the western Earth Kingdom, "
    #             "eastern Fire Nation, and the United Republic of Nations. It is part of the larger "
    #             "'western seas', and connected to West Lake, which is located southwest of Ba Sing Se."
    #             "The sea serves as a route for trading operations and is most notably the location of "
    #             "Crescent Island, once the site of the Fire Temple, and the seedy merchants pier, "
    #             "an important black market trading center. The Mo Ce Sea experienced countless naval "
    #             "battles during the Hundred Year War and played host to a massive Fire Navy blockade "
    #             "aimed at keeping all outsiders from Fire Nation waters. It also connects to Republic "
    #             "City through an inlet known as Yue Bay.",
    #     "color": discord.Color.from_rgb(113, 24, 222),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/a/ad/Blockade.png/revision/latest/scale-to-width-down/666?cb=20130622203336"
    # },
    # "Whaletail Island": {
    #     "desc": "Whaletail Island is a large island situated off of the southwestern coast of the "
    #             "Earth Kingdom and among the Southern Air Nomad archipelago. "
    #             "The island gets its name from its distinctive shape, which on maps bears an "
    #             "uncanny resemblance to a whale's tail.",
    #     "color": discord.Color.from_rgb(113, 24, 222),
    #     "img": "https://static.wikia.nocookie.net/avatar/images/a/a3/Whaletail_Island.png/revision/latest/scale-to-width-down/666?cb=20130701092431"
    # },
}

