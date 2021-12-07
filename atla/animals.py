
"""
Pet ideas and info

STATUSES        |       chance to find
-find nothing           62%
-common                 20
-uncommon               10
-rare                   5%
-endangered             2.5%
-critically endangered  0.5%

ROLES
-predator
-forager
-thief
-utility

ATTRIBUTES
-health (hp)
-intelligence (int)
-agility (agi)
-strength (str)

QUIRKS
-stubborn
-independent
-witty
-loyal
-aggressive
-scaredy cat

HIERARCHY CYCLE (has very small effect)
fire > air
water > fire
earth > water
air > earth

"""

#AIR NOMADS
pets = {
    "Flying bison": {
        "desc": "Large, flying mammal sacred to the Air Nomads",
        "img": "https://static.wikia.nocookie.net/avatar/images/3/37/Flying_bison_family.png/revision/latest/scale-to-width-down/700?cb=20130928143425",
        "habitat": [
            "Eastern Air Temple",
            "Northern Air Temple",
            "Southern Air Temple",
            "Western Air Temple",
            "Boiling Rock",
            "Ember Island",
            "Fire Fountain City",
            "Fire Nation Capital",
            "Hira'a village",
            "Jang Hui",
            "Shu Jing",
            "Sun Warriors' ancient city",
            "Air Temple Island"
        ],
        "status": "endangered",
        "affinity": "air",
        "bending": "air",
        "food": "herbivore",
        "autonomy": 9,
        "stubborness": 6,
        "strength": 8,
        "agility": 3,
        "attack": 150,
        "defense": 450,
        "resistance": [],
        "weakness": [],
        "min_health": 1000,
        "max_health": 5000,
        "time_to_adult": 10,
    },
    "Ring-tailed winged lemur": {
        "desc": "The ring-tailed winged lemur is a small animal closely related to the winged lemur. The species was discovered after the end of the Hundred Year War, and these creatures reside at the different air temples.",
        "img": "https://static.wikia.nocookie.net/avatar/images/f/f3/Ring-tailed_winged_lemur.png/revision/latest/scale-to-width-down/500?cb=20150627131941",
        "habitat": [
            "Air Temple Island",
            "Southern Air Temple"
        ],
        "status": "common",
        "affinity": "air",
        "bending": None,
        "food": "herbivore",
        "autonomy": 9,
        "stubborness": 5,
        "strength": 1,
        "agility": 9,
        "attack": 150,
        "defense": 450,
        "resistance": "resistances",
        "weakness": "weaknesses",
        "min_health": 1000,
        "max_health": 5000,
        "time_to_adult": 10,
    },
    "Winged lemur": {
        "desc": "The winged lemur is a small, energetic animal that is critically endangered. "
                "Momo is the only known survivor of winged lemurs that survived the Air "
                "Nomad Genocide, though the ring-tailed winged lemur, a closely related species, "
                "was discovered after the end of the Hundred Year War.",
        "img": "https://static.wikia.nocookie.net/avatar/images/6/67/Winged_lemur.png/revision/latest/scale-to-width-down/666?cb=20140108092622",
        "habitat": [
            "Eastern Air Temple",
            "Northern Air Temple",
            "Southern Air Temple",
            "Western Air Temple"
        ],
        "status": "critically endangered",
        "affinity": "air",
        "bending": None,
        "food": "herbivore",
        "autonomy": 9,
        "stubborness": 5,
        "strength": 1,
        "agility": 9,
        "attack": 150,
        "defense": 450,
        "resistance": "resistances",
        "weakness": "weaknesses",
        "min_health": 1000,
        "max_health": 5000,
        "time_to_adult": 10,
    },
    "Koalaotter": {
        "desc": "The koalaotter is a furry, aquatic mammal native to the North Pole and the surrounding Northern Sea.",
        "img": "https://static.wikia.nocookie.net/avatar/images/f/f0/Koalaotter.png/revision/latest/scale-to-width-down/666?cb=20140119103850",
        "habitat": [
            "Northern Water Tribe"
        ],
        "status": "common",
        "affinity": "water",
        "bending": None,
        "food": "herbivore",
        "autonomy": 9,
        "stubborness": 6,
        "strength": 8,
        "agility": 3,
        "attack": 150,
        "defense": 450,
        "resistance": [],
        "weakness": [],
        "min_health": 1000,
        "max_health": 5000,
        "time_to_adult": 10,
    }
}


#WATER TRIBE

"""
Aquatic/semiaquatic
Arctic hippo — Mammal that lives in the South Pole and is hunted for its blubber.[11]
Arctic seal — Swimming mammal native to the South Pole.[12]
Cuttlefish — Used to make paint that is applied for ceremonial markings.[13]
Dolphin piranha — A marine animal capable of eating humans.[14]
Fish — Various species are typically relied on for food in the Water Tribe.[5]
Halibut[14]
Koalaotter — Oceanic mammal with gray fur and large ears.[15]
Octopus — Cephalopod that lives in the sea.[11]
Otter penguin — Penguin with four flippers, used by Water Tribe people as sledges.[5]
Penguin fish — Gray fish with pink fins. It has a large eye in between its gills and its mouth.[16]
Polar orca[17]
Puffin-seal — Hybrid animal whose meat is made into sausages.[18]
Seal — Mammal whose skin is used to build tents.[16]
Sea sponge — Aquatic invertebrate.[19]
Tiger seal — Striped brown seal.[5]
Tiger shark — A powerful animal that is a cross between a tiger and a shark.[20]
Turtle seal — Brown seal with a hard shell, native to the North Pole.[19]
Whale-walrus — Creature whose blubber is used to make lamp oil.[18]
Whale — One of the few non-hybrid animals.[21]

Terrestrial
Arctic camel — A thick furred, two humped animal from the Southern Water Tribe used for transportation.[6]
Arctic hen — Arctic bird bred for its meat in the Southern Water Tribe; tastes similar to the possum chicken.[1]
Buffalo yak — Four-legged, furry, horned mammal used for transportation.[15]
Ice crawler — An arctic creature adapted to cold temperatures.[16]
Mink snake — Lives in the South Pole; known to bite humans.[22]
Polar bear — Non-hybridized arctic creature native to the Southern Water Tribe. Bones used in crafting weapons[23] and pelts for carpets.[24]
Polar bear dog — A large, four-legged wild carnivore; it was historically feared and hunted by the Water Tribe but can be tamed.[25]
Polar dog — Large dog; kept in Southern Water Tribe villages as a pet.[5]
Polar leopard — White leopard that preys on turtle seals; used for clothing in the Southern Water Tribe.[26]
Snow leopard caribou — Large feline used as a mount by warriors in the South Pole.[27]
Snow rat — Rodent-like creature native to the South Pole; a character in local folktales.[27]
White hamster — Small, white rodent.[5]
Wolf — Canine that inhabits the North[28] and South Pole. One of the few non-hybrid animals.[nb 1]
Yak — Large, four-legged herbivore. One of the few non-hybrid animals.[28]
"""

#EARTH KINGDOM
"""
Aquatic/semiaquatic
Catgator — Fierce reptile endemic to the Foggy Swamp and characterized by its feline barbels.[1]
Creeping slime — An "algaelike [sic] mass that crawls up the walls of the sewers in Omashu".[29]
Eel hound — Amphibious four-legged creature; used for quick transportation over both land and water.[8]
Eel swan — An elegant animal from which many upper-class topiaries are based.[30]
Elbow leech — Enormous parasitic worm that attaches to elbows and feeds on human blood.[1]
Elephant koi — Massive oceanic koi fish.[31]
Frog — Amphibian that lives in and near water.
Frog squirrel — Small hybrid creature that dwells in the Foggy Swamp.[32]
Flying fishopotamus — Combination of a hippo and a fish that people often ride for entertainment.[33]
Hippo — Large, semi-aquatic mammal.
Horned toad — Large amphibian with black horns.[34]
Jellynemone[35]
Killer shrimp — Ocean-dwelling crustacean.[36]
Lobster — Crustacean that can be consumed as food.[37][38]
Purple pentapus — Small cephalopod with five tentacles.[39]
Serpent — Large aquatic creature that inhabits the East and West Lakes[12] and is capable of dismantling a Fire Nation cruiser.[40]
Se tu — Large green catfish.[41]
Skunk fish — Foul-smelling, oily fish.[42]
Turtle duck — Duck with a protective green shell, can be domesticated and cooked.[43]
Unagi — Enormous eel that inhabits the South Sea near Kyoshi Island.[31]
Wood frog — Small amphibian, can be used for medicinal purposes when frozen.[44]

FLYING
Ant fly — Buzzing, flying insect that is known to inhabit the Lower Ring of Ba Sing Se.[45]
Blue jay — Bird with blue feathers.[11]
Bumble fly — Buzzing, flying insect.[46]
Butterfly — Flying insect.[29]
Buzzard wasp — Enormous flying insect that resides within the Si Wong Rock.[3]
Cat owl — Large, predatory bird with feline facial features.[36]
Cranefish — Noisy birds found near coastlines.[47]
Dove — Agile white bird.[22]
Dragonfly — Flying, serpentine lizard that resembles a dragon.[48]
Duck — Farmed bird; often roasted.[49]
Giant fly — Giant bug regularly consumed by the Foggy Swamp Tribe.[1]
Glowfly — Bioluminescent fly.[1]
Iguana parrot — Green reptilian bird with large talons.[50]
Raccoon-crow — Winged creature that enjoys feeding off pumpkins.[51]
Scorpion bee — Flying insect that gathers in large swarms and stings ferociously when aggravated.[52]
Screeching bird — White and gray bird with a shrill, piercing call.[1]
Sea vulture — Scavenger bird that inhabits the western coast of the Earth Kingdom.[53]
Songbird — A musical bird prized by collectors in Qinchao Village.[54]
Sooty copper fritillary — Orange and yellow butterfly tracked by miners to uncover new mineral deposits.[55]
Sparrowkeet — Small, colorful bird sometimes kept as a pet.[36]
Spider wasp — Cross between a spider and a wasp; known to have inhabited Yu Dao.[56]
Viper bat — Serpent-like creature with bat wings found in caves.[57]
Wolfbat — Large, snub-nosed bat that resides within the Cave of Two Lovers.[49]

TERRESTRIAL
Ant — Small insect that lives in large colonies.[37]
Armadillo lion — Animal that can roll up when tensed.[58]
Badgermole — Enormous, subterranean blind mammals; the original earthbenders.[49]
Bear — Large brown, non-hybrid mammal known to hibernate; extremely rare.[36][59]
Beetle worm — Worm and beetle hybrid that is occasionally used as an ingredient in soup.[57]
Boar-q-pine — Large wild boar covered in sharp, detachable spines.[60]
Cabbage slug — Small yet destructive agricultural pest.[12]
Camelephant — Four-legged mammal with a long nose; used for transportation.[61]
Canyon crawler — Insectoid, six-eyed, omnivorous creatures native to the Great Divide.[2]
Cat — There are numerous subspecies of cats, including a fluffy white tabby with green eyes, slim beige cat with patches of brown, and a bearded feline.[44][62]
Chameleon — Small, color-changing lizard with yellow eyes and a crest on its head.[26]
Chicken — Flightless bird bred for meat and eggs.
Crococat — Domesticated feline with the scaled back and abdomen of a crocodile.[63]
Deer dog — Domesticated canine with antlers found in the Si Wong Desert.[64]
Dog — Largely domesticated four-legged mammal.[65]
Elephant — Large terrestrial mammal known for its oversized ears.[55]
Elephant mandrill — Mandrill and elephant cross.[48]
Elephant rat — Black rodent with a large snout.[26]
Fire ferret — Red arboreal mammal common to bamboo forests.[66]
Fox antelope — Horned four-legged herbivore with a tail.[36]
Gecko — A small lizard able to quickly scale walls; inspiration for the Earth Rumble fighter of the same name.[67]
Gemsbok bull — Stocky brown animal with large horns.[48]
Giant night crawler — Giant worm.
Giant rhinoceros beetle — Giant beetle; used for transportation.[60]
Gilacorn — Small desert-dwelling, egg-stealing lizard.[60]
Goat dog — Small, shaggy, white canine kept as a pet.[48]
Gopher — A burrowing rodent; inspiration for the Earth Rumble fighter of the same name.[68]
Gopher bear — Cross between a gopher and a bear.[36]
Goat gorilla — Aggressive primate which inhabits secluded mountains and woodland; are sometimes held in captivity and tamed.[62]
Hermit marmoset — Chimerical creature with a strong shell that can last for centuries, which is often collected by shell connoisseurs.[69]
Hog — Wild mammal hunted for food in forested regions.[70]
Hog monkey — Forest-dwelling ape with a squashed face.[70]
Hopping llama[71]
Hoppy possum — Cross between a frog and a possum.[29]
Hybrid pigs — Includes the wooly-pig, moo-sow, picken, pigster, pig deer, bull pig, and pig chicken.[72][73]
Jackalope — Jackrabbit with large antlers.[60]
Leech-a-pillar — Leech and caterpillar cross.[29]
Lop-eared rabbit — Nimble rabbit with long, drooping ears.[62]
Meadow vole — Small white rodent.[11]
Ostrich horse — Large brown bird commonly used for transportation.[74]
Platypus bear — Bear with a large bill and flat tail; lays edible eggs.[41]
Poodle monkey — Domesticated simian pet.[48]
Possum chicken — Bird hunted in the Foggy Swamp; tastes similar to arctic hen.[1]
Prickle snake — Serpentine creature which is known to hide in sleeping bags, posing a danger to its occupier.[10]
Pygmy puma — Smaller and sleeker species of puma bred for and adapted to living in a compact city environment.[48]
Quilled chameleon — Reptile found in the densely forested regions.[26]
Rabaroo — Cross between a rabbit and kangaroo; young rabaroos are nurtured in their mothers' pouch.[48]
Saber-tooth moose lion — Moose and lion cross; cubs are not aggressive, but mature females are protective of their young.[75]
Sand shark — Massive shark-like predator that inhabits the inner regions of the Si Wong Desert.[76]
Scorpion — Venomous arachnid found in the Si Wong Desert.
Shirshu — Large, eyeless mammal with a pink, star-shaped nose; has a keen sense of smell used for tracking and navigation.[11]
Singing groundhog — Small, brown, and furry rodent with a musical call.[65]
Skunk bear — Cross of a skunk and a bear.[36]
Sour beetle — Only creature in the Si Wong Desert the giant gilacorn would not eat. According to legend, the headpieces worn by beetle-headed merchants were crafted to mimic the appearance of a sour beetle, an intuitive trick that allowed the tribesmen to deceive gilacorns and avoid being attacked.[77]
Spider — Eight-legged arachnid capable of quickly weaving a web.[26]
Spidersnake — Ten-eyed chimerical creature known to inhabit the Earth Kingdom. Cross between a spider and a snake. Its extract, very rare and expensive, can be used to change one's eye color.[78] "Killing two spidersnakes with one stone" is a saying that involves the creature.[79] In gambling, rolling two fives on a pair of dice is known as "spidersnake eyes".[72]
Sugar glider — Small mammal indigenous to forests. It has membranes between its legs that enable it to glide.[34]
Tigerdillo — Armadillo and tiger cross.[48]
Turkey duck — Turkey and duck hybrid.[41]
"""

#FIRE NATION
"""
Aquatic/semiaquatic
Badgerfrog — Green and brown frog with a trim of white fur.[80]
Clam — Mollusk found in the Jang Hui River; outer shell blisters when its environment is ravaged by water pollution.[81]
Coral urchin — A cross between a coral and a sea urchin; inspiration for the Coral Urchin Noodle Shop.[82]
Flying dolphin fish — A cross between a dolphin and a flying fish; can be ridden for recreational purposes.[83]
Iguana seal — Green aquatic reptile characterized by its unusual call.[61]
Manatee whale — Large aquatic mammal used to tug boats over the sea.[84]
Reefcrab — Known to inhabit jagged rocks along the southern coastline of Shuhon Island. Local birds prey upon reefcrabs when there is no refuse to eat.[17]
Silverskim fish — A migrating fish drawn to areas of heavy rain and caught in nets.[85]
Turtle crab — Crab with a protective turtle shell.[56]
Turtle duck — Duck with a protective green shell.[72]
Two-headed fish — Mutated fish spawned by the contamination of the Jang Hui River.[81]

Flying
Dragon — Large, flying reptile with a long body; the original firebenders.[74]
Eagle hawk — Cross between an eagle and a hawk.[86]
Flutter bat — A large bat found in the Fire Nation; it is a cross between a bat and a butterfly or a moth.[87]
Hawk — Non-hybridized hawk.
Lion vulture — Vulture and lion cross.[60]
Messenger hawk — Non-hybridized bird of prey with dark red or brown feathers and a lighter underside. It is used to deliver messages.[88]
Phoenix — Large bird commonly associated with the element of fire and a symbolic representation of the Phoenix King's power.
Raven eagle — Avian animal that can be trained to intercept messenger hawks.[84]
Sea raven — Stylistically depicted in the emblem of the Southern Raiders.[89]
Toucan puffin — Sea bird with a large yellow bill.[61]

Terrestrial
Aardvark sloth — Used in the Sun Warriors' ancient city to clean off slime.[90]
Armadillo bear — Large bear with a hard, segmented shell.[91]
Cavehopper — White arthropod with four legs.[61]
Dragon moose — Used for pulling carriages.[88]
Elephant rat — Elephant and rat cross.[92]
Hippo cow — Domesticated omnivorous mammal with black spots.[61]
Hippo-ox — Eaten as a delicacy.[93]
Koala sheep — Koala and sheep hybrid.[94]
Komodo chicken — A cross between a komodo dragon and a chicken; can be consumed as food.[61]
Komodo rhino — Ferocious creature characterized by its versatility and ability to function over many different types of terrain; it is therefore useful as a cavalry mount, but is also used to make komodo sausages.[31]
Mongoose lizard — Mongoose and basilisk lizard cross used for transportation.[95]
Puma goat — A cross between a puma and a goat.[96]
Snail sloth — Cross between a snail and a sloth and the slowest creature in the world.[97]
Squirrel toad — A small forest dwelling animal, it is a cross between a squirrel and a toad.[87]
Tiger monkey — Hybrid of a tiger and a monkey.[98]
Tigerdillo — A hybrid between a tiger and an armadillo; known for its roar[99] and defensive nature.[100]
"""

#UNITED REPUBLIC OF NATIONS
"""
Dragonfly hummingbird — a flying creature with the head, legs, and chest of a hummingbird, while sporting the wings, scales, and tail of a dragonfly. It can fly in any direction, which gave Asami Sato the idea to design a flying mecha suit after its image.[102]
Elephant rhino — Elephant and rhinoceros hybrid.[20]
Fish — Aquatic fauna found in the ponds of Avatar Korra Park.[103]
Monkey marmot — Hybrid animal with a reputation for stubbornness; according to Varrick they cannot be forced to do anything.[104]
Lizard crow — Lizard and crow cross that lives in urban areas.[105]
Poodle pony — Cross between a poodle and a pony.[46]
Pythonaconda — Cross between a python and an anaconda.[106]
Ring-tailed winged lemur — Flying mammal found on Air Temple Island; closely related to the winged lemur.[107]
Rooster pigeon — Sits on the telephone wires in Republic City, especially by the docks.[104]
Spider rat — Lives within the houses of Republic City and is considered to be an urban pest.[108]
Weasel snake — Weasel and snake hybrid.[66]
"""

#SPIRIT WORLD
"""
Catgator spirit — Reptile living in aquatic regions of the Spirit World, which can grow much larger than its counterpart from the natural world, and has spiritual abilities.[109][110]
Curly-tailed blue nose — Primate with brown fur.[111]
Dragonfly bunny spirit — Colorful, bunny-like spirits capable of flight.[112]
Forest spirit — Supernatural entity that watches over the forested regions of the northwestern Earth Kingdom.[113]
Giant wolf — Creature identical to an actual wolf with the exception of its gargantuan size.[111]
Hei Bai — Guardian spirit of a forest that normally assumes the form of a panda bear, but transforms into an aggressive monster with six limbs when enraged.[74]
Knowledge Seekers — Foxes that assist the knowledge spirit, Wan Shi Tong.[65]
Koi fish — Physical manifestation of the spirits Tui and La, who correspond with the Moon and Ocean, respectively. Two fish are found in the Northern Water Tribe's Spirit Oasis, one of which is primarily white and the other black. They continuously swim in a circle, performing an eternal dance of push and pull.[111]
Meerkat prairie dog spirit — A cross between a meerkat and a prairie dog.[109]
Moth wasp — Moth and wasp cross; the wolf spirit has the ability to breathe these.[73]
Spirit World firefly — Bioluminescent insect.[111]
Wolf spirit — Spirit living near Hira'a. It is extremely large and has the ability to breathe moth wasps.[73]
"""

#OTHER
"""
Angler termite — Cross between an angler and a termite that forms colonies in vast complex mounds.[114]
Bunch hornet — A type of flying insect that disguises itself as fruit.[115]
Cat deer — Cross between a cat and a deer; it can be domesticated and is large enough to be ridden.[116]
Chicken lizard — Cross between a chicken and a lizard.[96]
Cricket snail — Cross between a cricket and a snail.[117]
Falconfox — Feathered cross between a falcon and a fox.[118]
Flying boar — Symbol of the Beifong family.[37]
Fox — A four-legged creature that resembles a falconfox, only without the beak and the feathers.[118]
Jaguar beetle — An insect that lives in mounds created by angler termites after they have moved on to form other colonies.[114]
Lion elephant — Cross between a lion and an elephant.
Lion turtle — An ancient species that can grow to immense sizes. Vegetation will occasionally sprout on its back, and cities are sometimes built on its shell.[65][115]
Moth — An insect drawn to light and known to cause damage to some cloth materials, such as tents.[119][120]
Meerpenguin — Cross between a meerkat and a penguin.[121]
Opossum bat — Cross between an opossum and a bat, often used as an idiom ("playing opossum bat") to describe when someone is feigning defeat, death, illness, etc.[91]
Peacock pigeon — Cross between a peacock and a pigeon that lived during Wan's time.[115]
Pheasant squirrel — Cross between a common pheasant and a squirrel.[122]
Rhino lion — Cross between a rhinoceros and a lion.[20]
Skunk squirrel — Cross between a skunk and a squirrel that lived in Wan's time.[115]
Spider cat — Hybrid creature with brown fur.[65]
Shark squid — A cross between an squid and a shark that is considered powerful and scary.[14]
Squirrel — Small rodent.
Stingjelly — Cross between a stingray and jellyfish. It produces a sticky-sweet-smelling venom that is used in poison training, as it immobilizes the body to near paralysis and disorients the senses.[123][124]
Tea weevil — A type of beetle that can damage tea crops.[125]
Two-headed rat viper — Venomous snake with two heads.[89]
Vine cobra — A type of spitting animal.[126]
Walrus yak — Cross between a walrus and a yak.[65]
Webbed leopard — Known to ambush prey by dropping out of trees.[127]
Winged eel — Known to inhabit the Mo Ce Sea.[128]
Woodpecker lizard — Cross between a woodpecker and a lizard that lived during Wan's time.[115]
Zebra frog — Cross between a zebra and a frog.[129]
"""