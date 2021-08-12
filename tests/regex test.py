import re

msg = 'Tribe Ark Titans, ID 1094815690: Day 255, 15:50:03: <RichColor Color="1, 0, 0, 1">Tribemember Titan - Lvl 37 was killed by a Terror Bird - Lvl 253!</>)'
regex = r'(?i)Tribe (.+), ID (.+): (Day .+, ..:..:..): .+>(.+)<'


tribe = re.findall(regex, msg)
name = tribe[0][0]
tribe_id = tribe[0][1]
time = tribe[0][2]
action = tribe[0][3]

print(f"Tribe name: {name}\nID: {tribe_id}\nTime: {time}\nAction: {action}")