import os
import re
import sys


oropuare = "aāeēiīoōuū"
orokati = "hkmnprtwŋƒ"
no_tohutō = ''.maketrans({'ā': 'a', 'ē': 'e', 'ī': 'i', 'ō': 'o', 'ū': 'u'})
arapū = "AaĀāEeĒēIiĪīOoŌōUuŪūHhKkMmNnPpRrTtWwŊŋƑƒ-"


def whakatakitahi(tauriterite):
    # If passed the appropriate letters, return the corresponding symbol
    oro = tauriterite.group(0)
    if oro == 'ng':
        return 'ŋ'
    elif oro == 'w\'' or oro == 'w’' or oro == 'wh':
        return 'ƒ'
    elif oro == 'Ng' or oro == 'NG':
        return 'Ŋ'
    else:
        return 'Ƒ'


def whakatakirua(tauriterite):
    # If passed the appropriate symbol, return the corresponding letters
    oro = tauriterite.group(0)
    if oro == 'ŋ':
        return 'ng'
    elif oro == 'ƒ':
        return 'wh'
    elif oro == 'Ŋ':
        return 'Ng'
    else:
        return 'Wh'


def hōputu(kupu, hōputu_takitahi=True):
    # Replaces ng and wh, w', w’ with ŋ and ƒ respectively, since Māori
    # consonants are easier to deal with in unicode format
    # The Boolean variable determines whether it's encoding or decoding
    # (set False if decoding)
    if isinstance(kupu, list):
        if hōputu_takitahi:
            return [re.sub(r'(w\')|(w’)|(wh)|(ng)|(W\')|(W’)|(Wh)|(Ng)|(WH)|(NG)', whakatakitahi, whakatomo) for whakatomo in kupu]
        else:
            return [re.sub(r'(ŋ)|(ƒ)|(Ŋ)|(Ƒ)', whakatakirua, whakatomo) for whakatomo in kupu]
    elif isinstance(kupu, dict):
        if hōputu_takitahi:
            return [re.sub(r'(w\')|(w’)|(wh)|(ng)|(W\')|(W’)|(Wh)|(Ng)|(WH)|(NG)', whakatakitahi, whakatomo) for whakatomo in kupu.keys()]
        else:
            return [re.sub(r'(ŋ)|(ƒ)|(Ŋ)|(Ƒ)', whakatakirua, whakatomo) for whakatomo in kupu.keys()]
    else:
        if hōputu_takitahi:
            return re.sub(r'(w\')|(w’)|(wh)|(ng)|(W\')|(W’)|(Wh)|(Ng)|(WH)|(NG)', whakatakitahi, kupu)
        else:
            return re.sub(r'(ŋ)|(ƒ)|(Ŋ)|(Ƒ)', whakatakirua, kupu)

def kōmiri_kupu(kupu_tōkau, kūare_tohutō=True):
    # Removes words that contain any English characters from the string above,
    # returns dictionaries of word counts for three categories of Māori words:
    # Māori, ambiguous, non-Māori (Pākehā)
    # Set kūare_tohutō = True to become sensitive to the presence of macrons when making the match

    # Splits the raw text along characters that a
    kupu_hou = re.findall('(?!-)(?!{p}*--{p}*)({p}+)(?<!-)'.format(
        p='[a-zāēīōū\-’\']'), kupu_tōkau, flags=re.IGNORECASE)

    rootpath = ''
    try:
        root = __file__
        if os.path.islink(root):
            root = os.path.realpath(root)
        dirpath = os.path.dirname(os.path.abspath(root)) + '/helper_files'
    except:
        print("I'm sorry, but something is wrong.")
        print("There is no __file__ variable. Please contact the author.")
        sys.exit()

    # Reads the file lists of English and ambiguous words into list variables
    kōnae_pākehā, kōnae_rangirua = open(dirpath + "/kupu_kino.txt" if kūare_tohutō else dirpath + "/kupu_kino_kūare_tohutō.txt", "r"), open(
        dirpath + "/kupu_rangirua.txt" if kūare_tohutō else dirpath + "/kupu_rangirua_kūare_tohutō.txt", "r")
    kupu_pākehā = kōnae_pākehā.read().split()
    kupu_rangirua = kōnae_rangirua.read().split()
    kōnae_pākehā.close(), kōnae_rangirua.close()

    # Setting up the dictionaries in which the words in the text will be placed
    raupapa_māori, raupapa_rangirua, raupapa_pākehā = {}, {}, {}

    kupu_hou, kupu_pākehā, kupu_rangirua = hōputu(
        kupu_hou), hōputu(kupu_pākehā), hōputu(kupu_rangirua)

    # Puts each word through tests to determine which word frequency dictionary
    # it should be referred to. Goes to the ambiguous dictionary if it's in the
    # ambiguous list, goes to the Māori dictionary if it doesn't have consecutive
    # consonants, doesn't end in a consnant, doesn't have any english letters
    # and isn't one of the provided stop words. Otherwise it goes to the non-Māori
    # dictionary. If this word hasn't been added to the dictionary, it does so,
    # and adds a count for every time the corresponding word gets passed to the
    # dictionary.

    for kupu in kupu_hou:
        if kupu.lower() in kupu_rangirua:
            kupu = hōputu(kupu, False)
            if kupu not in raupapa_rangirua:
                raupapa_rangirua[kupu] = 0
            raupapa_rangirua[kupu] += 1
            continue
        elif not (re.compile("[{o}][{o}]".format(o=orokati)).search(kupu.lower()) or (kupu[-1].lower() in orokati) or any(pūriki not in arapū for pūriki in kupu.lower()) or (kupu.lower() in kupu_pākehā)):
            kupu = hōputu(kupu, False)
            if kupu not in raupapa_māori:
                raupapa_māori[kupu] = 0
            raupapa_māori[kupu] += 1
            continue
        else:
            kupu = hōputu(kupu, False)
            if kupu not in raupapa_pākehā:
                raupapa_pākehā[kupu] = 0
            raupapa_pākehā[kupu] += 1

    return raupapa_māori, raupapa_rangirua, raupapa_pākehā


def get_percentage(kōwae):
    # Uses the kōmiri_kupu function from the taumahi module to estimate how
    # Much of the text is Māori. Input is a string of text, output is a percentage string

    # Gets the word frequency dictionaries for the input text
    raupapa_māori, raupapa_rangirua, raupapa_pākehā = kōmiri_kupu(kōwae, False)

    # Calculates how many words of the Māori and English dictionary there are
    tatau_māori = sum(raupapa_māori.values())
    tatau_pākehā = sum(raupapa_pākehā.values())
    tatau_tapeke = tatau_māori + tatau_pākehā

    # Provided there are some words that are categorised as Māori or English,
    # It calculates how many Māori words there are compared to the sum, and
    # Returns the percentage as a string
    if tatau_tapeke != 0:
        return "{:0.2f}%".format((tatau_māori / tatau_tapeke) * 100)
    else:
        return "0.00%"


if __name__ == '__main__':
    text = """
THE pages of the present number of the Karere are principally occupied with notifications of land acquired by the Government in various parts of this island, which are published for the information of our Maori readers. We have therefore little space for other matter. We wish, however, to repeat here what we have on former occasions endeavoured to impress upon the minds of our readers in reference to lands which are bought by the Government from the Native owners. It is a mistake to regard such lands as having passed away for ever from the Maori people to be given exclusively to the Pakeha. They are sold by the Government under certain regulations to any one who will buy, whether Pakeha or Maori. We should be very glad to see the Maories coming forward more frequently than they do to purchase Government land. Money which is now often wasted in buying vessels which for want of proper management get out of KUA kapi nga wharangi o tenei Karere i nga panuitanga o nga whenua kua riro i te Ka- wanatanga i tenei wahi i tera wahi o te motu nei. Taia ana aua panuitanga hei mataki- taki iho ma nga tangata korero i tenei niu- pepa. Heoi, kahore he wharangi i toe mo etahi atu korero. Ko tenei, me puta ano te kupu kotahi nei, be kupu whakamahara ki a matou korero era atu Kawe mo te whenua. Kua ata ko - rerotia atu hoki e matou nga tikanga o nga whenua e hokona nei e te Kawanatanga i nga Iwi Maori nona aua wahi. He hori te ki, ko te rironga i te Kawanatanga, heoi, motu ra wa atu i te Maori, ake tonu atu. riro rawa atu ma te Pakeha anake. Kahore. Huaatu, e hokona atu ana aua whenua e te Kawanatanga ki nga tangata katoa e pai ki te hoko, ahakoa Pakeha ahakoa Maori. He Ture ano ia e takoto nei mo te hokonga o aua whenua. Ki ta matou, ka pai kia tokomaha nga tangata Maori hoko whenua i te Kawanatanga. E mea ana hoki to matou whakaaro, mehemea pea, ko etahi o nga moni e maumaua huhuakoretia nei i runga i te hoko kaipuke, mehemea ka utua ki te whenua, ka kitea he tikanga mo aua moni. Ko tenei, hokona ana ki te kaipuke,
    """
    print(get_percentage(text))