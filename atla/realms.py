import discord

realms = {
    # Air Nomads
    "Eastern Air Temple": {
        "desc": "The Eastern Air Temple was one of the two temples exclusively housing female airbenders. "
                "Like the other temples, its population was completely exterminated during the Air Nomad Genocide. "
                "Guru Pathik resided here for a considerable amount of time, "
                "as he waited years for Aang to come so he could teach the Avatar "
                "how to properly control the Avatar State.",
        "color": discord.Color.from_rgb(255, 255, 255)
    },
    "Northern Air Temple": {
        "desc": "The Northern Air Temple is a temple that hosted only male monks. "
                "It is located in the upper reaches of the northern Earth Kingdom, "
                "built upon a snow-capped mountain. This temple was also a victim of the "
                "Air Nomad Genocide, along with all the other air temples. By 100 AG, "
                "it had become renowned for its arbitrary colonization by Earth Kingdom refugees, "
                "who were led by the mechanist. Up to that point, the area had undergone rapid "
                "industrialization.",
        "color": discord.Color.from_rgb(255, 255, 255)
    },
    "Southern Air Temple": {
        "desc": "The Southern Air Temple was one of the four sanctuaries owned by the Air Nomads. "
                "It is the one located closest to the Southern Water Tribe and exclusively housed "
                "male airbenders. This region is notable for being the childhood home of Avatar Aang, "
                "and it was also the place where Avatar Roku learned airbending.",
        "color": discord.Color.from_rgb(255, 255, 255)
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
        "color": discord.Color.from_rgb(255, 255, 255)
    },
    # Water Tribe
    "Foggy Swamp": {
        "desc": "Though an outlying expanse of the tribe, this vast and mysterious wetland occupies a "
                "considerable portion of the southwestern Earth Kingdom. It provides an ideal residence "
                "for the Foggy Swamp Tribe, who are descended from immigrants of the Southern Water Tribe. "
                "The Swamp has an extensive array of fauna and flora, the latter of which are actually "
                "just a series of roots connected to one central tree, the towering banyan grove.",
        "color": discord.Color.from_rgb(0, 196, 245)
    },
    "Northern Water Tribe": {
        "desc": "The Northern Water Tribe is the largest division of its nation and is located on "
                "an island situated near the North Pole. The capital city, Agna Qel'a, prospers in "
                "its isolation. No attack from the Fire Nation on the city during the Hundred Year "
                "War ever ended in a loss for the tribe, including the tumultuous Siege of the North. "
                "After the fall of Ba Sing Se, the Northern Water Tribe boasted the only major city in "
                "the world to not be under Fire Nation jurisdiction.",
        "color": discord.Color.from_rgb(0, 196, 245)
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
        "color": discord.Color.from_rgb(0, 196, 245)
    },
    # Earth Kingdom
    # Central Regions
    "Full Moon Bay": {
        "desc": "Full Moon Bay is a secluded cove in East Lake, located just south of Ba Sing Se. "
                "It is the location of a hidden ferry station that refugees from all over the southern "
                "portion of the Earth Kingdom come to on their way to Ba Sing Se.",
        "color": discord.Color.from_rgb(12, 148, 0)
    },
    "Great Divide": {
        "desc": "The Great Divide is the largest canyon in the world. "
                "It is located in the rocky regions of the central Earth Kingdom.",
        "color": discord.Color.from_rgb(12, 148, 0)
    },
    "Si Wong Desert": {
        "desc": "The Si Wong Desert is the largest desert in the world. "
                "It is almost impossible to successfully navigate. "
                "It is sparsely inhabited by Si Wong tribes.",
        "color": discord.Color.from_rgb(12, 148, 0)
    },
    # Northeastern regions
    "Ba Sing Se": {
        "desc": "Ba Sing Se is the monolithic capital of the Earth Kingdom, "
                "encompassing nearly the entire northeast corner of the country. "
                "It was the last great Earth Kingdom stronghold after the fall of Omashu. "
                "Ba Sing Se means 'impenetrable city', an honorary reference to its two "
                "insurmountable walls, the gates of which have no hinges and can therefore not "
                "be opened in any way aside from the use of earthbending.",
        "color": discord.Color.from_rgb(12, 148, 0)
    },
    "Serpent's Pass": {
        "desc": "The Serpent's Pass is a narrow strip of land between the East and West Lakes that "
                "links the southern and northern halves of the Earth Kingdom. It is one of the very "
                "few direct paths to the capital, Ba Sing Se. The pathway is named after the serpent "
                "which guards the point at which the East and West Lakes meet. Here, the Serpent's Pass "
                "dips below the lakes for a limited distance. These adversities make the Serpent's Pass "
                "a typically avoided entryway into Ba Sing Se, and most refugees prefer to go by ferry "
                "instead.",
        "color": discord.Color.from_rgb(12, 148, 0)
    },
    # Northwestern regions
    "Merchant town": {
        "desc": "The merchant town is a minor trading settlement located high in the mountains of the "
                "northwestern Earth Kingdom. Historically, this region was the site of numerous airbender "
                "murders, as survivors of the genocide were tricked by firebenders into coming to this "
                "location when they heard rumors of its mysterious possession of Air Nomad relics. "
                "Such airbenders were consequently killed in a decisive ambush.",
        "color": discord.Color.from_rgb(12, 148, 0)
    },
    # Southern regions
    "Chin Village": {
        "desc": "Chin Village is a small town located on the cliffs of the Earth Kingdom's "
                "southwestern coast. It is named for Chin the Great, a warlord and conqueror "
                "who nearly conquered the Earth Kingdom. It plays host to the unique 'Avatar Day' "
                "festival, a celebration that used to be a celebration in hate of the Avatar but is "
                "now held in honor of the Avatar.",
        "color": discord.Color.from_rgb(12, 148, 0)
    },
    "Gaoling": {
        "desc": "Gaoling is a large town located within a mountain range in the southern Earth Kingdom. "
                "It is home to both the wealthy Beifong family and the Earth Rumble tournaments. "
                "An old, well-established city, Gaoling has a spectrum of people residing in it, "
                "ranging from the very rich to the very poor. Because it was not in a particularly "
                "strategic location, the town was left untouched by the Hundred Year War. "
                "This is evidenced by the attitude of many of its residents.",
        "color": discord.Color.from_rgb(12, 148, 0)
    },
    "Kyoshi Island": {
        "desc": "Kyoshi Island is a small island off the southern coast of the Earth Kingdom, "
                "dotted with many small villages. It is famous as the birthplace of Avatar Kyoshi, "
                "and as the home of the elite Kyoshi Warriors.[20] The island was created when Chin "
                "the Conqueror threatened to invade and conquer the former peninsula. "
                "Avatar Kyoshi separated Yokoya Peninsula from the Earth Kingdom mainland to keep her "
                "people safe from future threats.",
        "color": discord.Color.from_rgb(12, 148, 0)
    },
    "Omashu": {
        "desc": "Omashu is the second largest city in the Earth Kingdom and the capital of one of its "
                "provinces. Only Ba Sing Se, the titanic capital of the Earth Kingdom, is larger. "
                "It was one of the last great strongholds of the Earth Kingdom before its fall in the "
                "months before the end of the Hundred Year War, and a supplier of men and weaponry. "
                "Previously ruled by King Bumi, Omashu was taken over by the Fire Nation and renamed "
                "New Ozai. During the Day of Black Sun, King Bumi single-handedly liberated Omashu, "
                "and all the powerless firebenders abandoned the city.",
        "color": discord.Color.from_rgb(12, 148, 0)
    },
    "Zaofu": {
        "desc": "Zaofu is an autonomous city-state, located in the southwestern part of the "
                "Earth Kingdom, and the home of the Metal Clan. Founded by Suyin Beifong, "
                "the Clan's matriarch, Zaofu is constructed entirely out of metal and is regarded by "
                "some as the safest city in the world. It was annexed by the Earth Empire temporarily "
                "in 174 AG, but power over the city was returned to Suyin following Kuvira's surrender.",
        "color": discord.Color.from_rgb(12, 148, 0)
    },
    # Western regions
    "Cave of Two Lovers": {
        "desc": "Located near the city of Omashu in the Earth Kingdom, the Cave of Two Lovers is a "
                "secret tunnel that passes through a section of the Kolau Mountain Range. "
                "The tunnel is actually a giant underground labyrinth full of dangerous animals "
                "including wolfbats and badgermoles.",
        "color": discord.Color.from_rgb(12, 148, 0)
    },
    "Farming Village": {
        "desc": "This farming village is a small village located in the western Earth Kingdom. "
                "Zuko and Iroh traveled to the village so Iroh could receive treatment for a rash "
                "caused by the white jade plant.",
        "color": discord.Color.from_rgb(12, 148, 0)
    },
    "Gaipan": {
        "desc": "Gaipan is a small village located in the central Earth Kingdom. "
                "After being overtaken by the Fire Nation, it was evacuated shortly "
                "before being destroyed by a catastrophic flood.",
        "color": discord.Color.from_rgb(12, 148, 0)
    },
    "Mining village": {
        "desc": "The mining village is a medium-sized village located in the Earth Kingdom. "
                "It is located on the northwestern coast of the Earth Kingdom, "
                "and its inhabitants make a living by mining coal in several nearby mines.",
        "color": discord.Color.from_rgb(12, 148, 0)
    },
    "River village": {
        "desc": "The river village is located in the western Earth Kingdom, "
                "situated between the forks of a large river. It serves as a "
                "regional trading hub and ideal location for merchants to sell their wares.",
        "color": discord.Color.from_rgb(12, 148, 0)
    },
    # Fire nation
    "Boiling Rock": {
        "desc": "The Boiling Rock is a massive Fire Nation prison. Its name is derived from the "
                "fact that the prison is on an island in the middle of a boiling lake on a volcanic "
                "island. The Boiling Rock is where the most dangerous prisoners in the Fire Nation are "
                "held, domestic and foreign alike.",
        "color": discord.Color.from_rgb(112, 0, 0)
    },
    "Ember Island": {
        "desc": "Ember Island is a small resort located in the outer islands of the Fire Nation. "
                "It is home to many luxurious resorts and vacation homes for the wealthy and powerful. "
                "The beaches are among the most popular in the country and host many popular kuai ball "
                "games.",
        "color": discord.Color.from_rgb(112, 0, 0)
    },
    "Fire Fountain City": {
        "desc": "Fire Fountain City is a large, industrial city located in the Fire Nation. "
                "It is named for the large, fire-breathing statue of Fire Lord Ozai in its center. "
                "It is located on one of the many islands in the eastern half of the Fire Nation.",
        "color": discord.Color.from_rgb(112, 0, 0)
    },
    "Fire Nation Capital": {
        "desc": "The Fire Nation Capital is the seat of the government for the Fire Nation. "
                "It is home to the Fire Lord, the royal family, and nobles of the Fire Nation. "
                "The capital is located on the Capital Island, a larger island in the western region "
                "of the Fire Nation.",
        "color": discord.Color.from_rgb(112, 0, 0)
    },
    "Hira'a village": {
        "desc": "The village of Hira'a is a small settlement surrounded by mountains and lush "
                "forests and situated relatively close to the Forgetful Valley.",
        "color": discord.Color.from_rgb(112, 0, 0)
    },
    "Jang Hui": {
        "desc": "Jang Hui is a small, poor village located in the outer islands of the Fire Nation. "
                "Located on the Jang Hui River, this unique Fire Nation village is made up of floating "
                "houseboats connected together.",
        "color": discord.Color.from_rgb(112, 0, 0)
    },
    "Shu Jing": {
        "desc": "Shu Jing is a town located in the Fire Nation. Situated on a cliff above a river "
                "and waterfalls and surrounded by beautiful mountains, this is one of the many small, "
                "peaceful villages that are tucked away throughout the Fire Nation islands.",
        "color": discord.Color.from_rgb(112, 0, 0)
    },
    "Sun Warriors' ancient city": {
        "desc": "This location is a sprawling, ancient city that was thought to be an uninhabited ruin. "
                "Aang and Zuko discovered that the Sun Warrior civilization still existed here.",
        "color": discord.Color.from_rgb(112, 0, 0)
    },
    # United Republic of Nations
    "Harbor town": {
        "desc": "The harbor town is a small coastal settlement located in the southern United Republic "
                "of Nations. Despite its strategic location, the village managed to stay free from "
                "Fire Nation occupation during the Hundred Year War.",
        "color": discord.Color.from_rgb(222, 166, 24)
    },
    "Makapu Village": {
        "desc": "Makapu Village is a small farming town located in the northeastern United Republic "
                "of Nations on the slopes of Mt. Makapu, an active volcano. "
                "Volcanic eruptions have caused the soil around the volcano to become rich in minerals, "
                "making it perfect for agriculture. It was notable for being the residence of the "
                "fortuneteller Aunt Wu. The village is also home to the rare panda lily flower, "
                "which grows in and around the crater of the volcano, and which is commonly used "
                "as a symbol of everlasting love and unity.",
        "color": discord.Color.from_rgb(222, 166, 24)
    },
    "Republic City": {
        "desc": "Republic City is a large metropolis located in the lower areas of a mountainous region, "
                "with large bodies of water in the immediate vicinity. It was founded as the capital "
                "of the United Republic of Nations, a fifth nation created by Fire Lord Zuko and Avatar "
                "Aang after the end of the Hundred Year War.",
        "color": discord.Color.from_rgb(222, 166, 24)
    },
    "Seedy merchants pier": {
        "desc": "The seedy merchants pier is a small harbor and town in the southern "
                "United Republic of Nations. It is a tiny trading port with a seedy element. "
                "Here one can buy almost anything, from jewelry to pottery to musical instruments "
                "and trivial items. The seedy merchant's pier welcomes all nations so long as they "
                "have an inclination for a bargain.",
        "color": discord.Color.from_rgb(222, 166, 24)
    },
    "Senlin Village": {
        "desc": "Senlin Village is a small farming village located in the center of a dense forest "
                "in the southern United Republic of Nations. It was attacked by the spirit Hei Bai "
                "near the winter solstice of 99 AG.",
        "color": discord.Color.from_rgb(222, 166, 24)
    },
    "Taku": {
        "desc": "Taku is an abandoned city located along the coast of the United Republic of Nations. "
                "Prior to its destruction during the early stages of the Hundred Year War, "
                "the settlement was an important center of commerce.",
        "color": discord.Color.from_rgb(222, 166, 24)
    },
    "Yu Dao": {
        "desc": "Yu Dao was once an Earth Kingdom city that was established as the first of the "
                "Fire Nation colonies. It was located in a wide, flat valley which was bounded by "
                "rocky terrain on all sides. The city was enclosed by a sandstone wall with one opening "
                "which served as the gateway to the city. Yu Dao's streets were lined by predominantly "
                "low rise buildings which were built in a unique style that combined Earth Kingdom and "
                "Fire Nation architecture.",
        "color": discord.Color.from_rgb(222, 166, 24)
    },
    "Air Temple Island": {
        "desc": "Air Temple Island is a small isle located off the coast of Republic City in Yue Bay. "
                "The island is formally independent of the nearby United Republic, "
                "and is under the sole jurisdiction of the new Air Nation. Comprised of several structures, "
                "the temple was built by Avatar Aang himself and is home to Tenzin, his wife Pema, "
                "and their four children Jinora, Ikki, Meelo, and Rohan, as well as the Air Acolytes. "
                "Also residing on the island are colonies of flying bison and ring-tailed winged lemurs.",
        "color": discord.Color.from_rgb(222, 166, 24)
    },
    # Neutral locations
    "Mo Ce Sea": {
        "desc": "The Mo Ce Sea is a small, open body of water between the Earth Kingdom and the "
                "Fire Nation. It extends from the Hu Xin provinces of the Earth Kingdom to the Crescent "
                "Island and from the Fire Islands to the western coast of the Earth Kingdom.",
        "color": discord.Color.from_rgb(113, 24, 222)
    },
    "Whaletail Island": {
        "desc": "Whaletail Island is a large island situated off of the southwestern coast of the "
                "Earth Kingdom and among the Southern Air Nomad archipelago. "
                "The island gets its name from its distinctive shape, which on maps bears an "
                "uncanny resemblance to a whale's tail.",
        "color": discord.Color.from_rgb(113, 24, 222)
    },
}

