import os

directory = 'H:\Drive\Pictures\Icons-Emojis\ArkDinos'
save_path = 'C:/Users/GAMER/Documents'
filename = 'ark'
image_url = 'https://www.dododex.com/media/creature/'
completename = os.path.join(save_path, filename+".yaml")
with open(completename, "a") as file:
    for filename in os.listdir(directory):
        name = os.path.splitext(filename)[0]
        dino_link_name = name.lower()
        stripped_name = dino_link_name.replace(" ", "")
        url = f"{image_url}{stripped_name}"
        print(name.capitalize())
        file.write(f"What Ark creature is this? {url}.png:\n- {name.capitalize()}\n")


