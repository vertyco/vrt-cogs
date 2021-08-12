import xbox
xbox.client.authenticate(login='firtyco@gmail.com', password='Lonewolf1!')
gt = xbox.GamerProfile.from_gamertag('itz0alex')
print(gt)