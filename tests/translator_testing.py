import googletrans
translator = googletrans.Translator()
test = translator.detect('Hola como estás')
print(test)
print(test.lang)
trans = translator.translate('Hola como estás', dest='es')
print(trans)
print(trans.text)
print(trans.src)

# <Translated src=ko dest=en text=Good evening. pronunciation=Good evening.>

# translator.translate('안녕하세요.', dest='ja')
# <Translated src=ko dest=ja text=こんにちは。 pronunciation=Kon'nichiwa.>

# translator.translate('veritas lux mea', src='la')
# <Translated src=la dest=en text=The truth is my light pronunciation=The truth is my light>