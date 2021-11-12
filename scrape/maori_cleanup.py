import re
from datetime import datetime

from scrape.maori_percentage_calculator import get_percentage

from bs4 import BeautifulSoup as bs

# Punctuation that will be searched for, and stripped respectively.
# The former indicates the end of a paragraph if followed by a new line character.
punctuations = ".!?"
speech_marks = "‘’\'\") "


class Issue:
    # This class takes a row from the index file it reads and attributes it to a class object for readability
    def __init__(self, row, last_row=None):
        self.newspaper = row[0]
        if len(row) == 3:
            self.issue = row[1]
            self.link = row[2]
        else:
            self.issue = ''
            self.link = row[1]

        if last_row:
            self.last_newspaper = last_row[1]
            self.last_issue = last_row[2]
            self.last_hau = last_row[3]
            self.last_text = last_row[9]
            self.last_link = last_row[10]
            self.last = True
        else:
            self.last = False


class Row:
    # This information sets up all the information that will be written to the text csv file, apart from the time of
    # retrieval, in a class object, to prevent the need for tuples, and for improved readability. The input is a
    # Issue class object, and the url of the page the text is extracted from The maori, ambiguous, english and
    # total attributes are updated per paragraph in the row_kaituhituhi function.
    def __init__(self, newspaper, link, rawtext):
        self.newspaper = newspaper.newspaper
        self.issue = newspaper.issue
        self.link = link
        # Extracts the soup of the issue's first page
        self.soup = bs(rawtext, 'html.parser')
        # Extracts the page number from the soup
        self.page_number = self.soup.find('b').text.split("page  ")[1]
        self.maori = 0
        self.ambiguous = 0
        self.english = 0
        self.total = 0
        self.percent = 0.00
        # Extracts the text from the page's soup
        self.text = get_plain_text(self.soup, self.page_number)
        self.content = ""
        self.last_row = newspaper.last


class BeginParagraph:
    # Sets up the 'left over paragraph' from the previous page in a class object for readability
    # The input is a Row class object.
    def __init__(self, source):
        self.page_number = source.page_number
        self.text = source.text
        self.link = source.link


def clean_whitespace(paragraph):
    return re.sub(r'\s+', ' ', paragraph).strip()


def get_plain_text(soup, page_number):
    # Extracts the text for all pages of the issue it has been passed.
    # It takes a tuple and a list. The tuple has the newspaper name, issue name
    # And issue link. The list is of tuples containing each page of the issue's
    # Number, soup and url. It outputs a list of tuples, which contain each page
    # Of an issue's number, text and url.

    # Simplify the soup to the area we are interested in
    plain_text = soup.select('div.documenttext')[0].find('td')

    # Must determine there is a div.documenttext, because .text will raise an error if it text_tōkau is None
    if plain_text is not None:
        if plain_text.text:
            # If it can find text, it returns it
            return plain_text.text
        else:
            # If there is no text found, print an error
            print("Failed to extract text from page " + page_number)
    else:
        print("Failed to extract text from page " + page_number)

    return None


def replace_regex(pattern, function_name, text):
    # Finds all matches to the input regex, in the input text, using the input string to determine what to replace
    # the match with The first argument is a regex expression, the second is a string containing a function name from
    # the page_number module, the third is the text that is to be modified
    matches = re.compile(pattern).findall(text)
    for match in matches:
        original_text = match[0].strip()
        text = " "
        if function_name == "rā_kupu":
            text += "<date>"
        elif function_name == "tāima_kupu":
            text += "<time>"
        else:
            text += "<number>"
        text += " "
        text = text.replace(original_text, text)
    return text


def clean_up(text):
    # The calls to these functions in page_number don't need to be made for the irstlm language model,
    # however replacements make the model more effective. Hence we use a string with the function of the page_number
    # module's name to represent the kind of object it is replacing.
    months = '(Hanuere|Pepuere|Maehe|Apereira|Mei|Hune|Hurae|Akuhata|Hepetema|Oketopa|Noema|Nowema|Tihema)'
    # Comma separated pound values, ending with common representations for shillings and pounds
    text = replace_regex(
        '((£?([1-9]\d{0,2}[,\/‘`´’\'\".][ ]?)(\d{3}[,\/‘`´’\'\".][ ]?)*\d{3}([.,]{2}\d{1,2}){1,2}))', "pakaru_moni",
        text)
    text = replace_regex(
        '(?i)(£?[1-9]\d{0,2}[,\/‘`´’\'\".][ ]?(\d{3}[,\/‘`´’\'\".]?[ ]?)+ ?l\.? ?( ?\d+ ?[ds]\.? ?){0,2})',
        "pakaru_moni", text)
    # Non-comma separated pound values, with the same endings
    text = replace_regex('(£?([1-9]\d*([.,]{2}\d{1,2}){1,2}))', "pakaru_moni", text)
    text = replace_regex('(?i)((£?[1-9]\d*( ?\d+ ?[lsd]\.? ?){1,3}))', "pakaru_moni", text)
    # Typical date format xx/xx/xx
    text = replace_regex('((\d{1,2}\/){1,2}\d{2})', "rā_kupu", text)
    # Other common date formats that involve words - e.g. the (day) of (month), (year); or (month) (day) (year)
    text = replace_regex('(?i)((\b|\W|\s|^)(te )\d{1,2}( [,o])? ' + months + ',? \d{4}(\b|\W|\s|\s|$|\W))',
                             "rā_kupu", text)
    text = replace_regex('(?i)((\b|\W|\s|^)\d{1,2}( [,o])? ' + months + ',? \d{4}(\b|\W|\s|\s|$|\W))', "rā_kupu",
                             text)
    text = replace_regex('(?i)(' + months + ',? \d{1,2},? \d{4}(\b|\W|\s|$))', "rā_kupu", text)
    text = replace_regex('(?i)((\b|\W|\s|^)\d{4},? ' + months + ')', "rā_kupu", text)
    text = replace_regex('(?i)(' + months + ',? \d{4}(\b|\W|\s|$))', "rā_kupu", text)
    text = replace_regex('(?i)((\b|\W|\s|^)(te )\d{1,2}( [,o])? ' + months + '(\b|\W|\s|$))', "rā_kupu", text)
    text = replace_regex('(?i)((\b|\W|\s|^)\d{1,2}( [,o])? ' + months + '(\b|\W|\s|$))', "rā_kupu", text)
    text = replace_regex('(?i)(' + months + ',? \d{1,2}(\b|\W|\s|$))', "rā_kupu", text)
    # Comma separated pound values with no suffixes
    text = replace_regex('(£([1-9]\d{0,2}[,‘`´’\'\".][ ]?)(\d{3}[,\/‘`´’\'\".][ ]?)*\d{3})', "pakaru_moni", text)
    # Other comma separated values, not financial
    text = replace_regex('(([1-9]\d{0,2}[,‘`´’\'\".][ ]?)(\d{3}[,\/‘`´’\'\".][ ]?)*\d{3})', "hōputu_tau", text)
    # Finds times separated by punctuation (with or without a space), optionally followed by am/pm
    text = replace_regex('(?i)((\d{1,2}\. ){1,2}(\d{1,2}) ?[ap]\.?m\.?)', "tāima_kupu", text)
    text = replace_regex('(?i)((\d{1,2}[,.:]){0,2}(\d{1,2}) ?[ap]\.?m\.?)', "tāima_kupu", text)
    text = replace_regex('((\d{1,2}\. ?){1,2}\d{1,2})', "tāima_kupu", text)
    # Deals with any leftover slash-separated values that weren't accepted by "tāima_text" by replacing the slashes
    # with words
    text = replace_regex('((\d{1,6}( \/ | \/|\/ |\/|\.)){1,5}\d{1,5})', "hautau_rānei_ira", text)
    # Finds all other monetary values
    text = replace_regex('(£(\d)+)', "pakaru_moni", text)
    # Finds all other numbers
    text = replace_regex('((\d)+)', "hōputu_tau", text)
    # Removes characters that aren't letters or spaces.
    text = re.sub(r'[^A-Za-zĀĒĪŌŪāēīōū!"#$%&\'()*+,./:;<=>?[\\]^_`‘’{|}-£´\s]', '', text)
    # Clears excess spaces
    return clean_whitespace(text)


def remove_punctuations(text):
    return re.findall(r'[\w\W]*?[{}][{}]*\n|[\w\W]+$'.format(punctuations, speech_marks), text)


def text_moroki(source, begin_paragraph):
    # It strips the text of any unnecessary trailing characters that could follow the end of the sentence,
    # such as quotation marks
    punctuationless_text = source.text.strip(speech_marks)

    # If there is anything left after these characters have been stripped (so as not to cause an error)
    if punctuationless_text:
        # If the last character of the string is an acceptable "end of paragraph" character, and there are preceeding
        # pages (i.e. it is not the last page of the issue since a paragraph will not continue over consecutive issues)
        if punctuationless_text[-1] not in punctuations \
                and source.soup.select('div.navarrowsbottom')[0].find('td', align='right', valign='top').a:
            # Then this paragraph will be carried over to the next page (the next time this function is called) by
            # using the global begin_paragraph variable

            # If there isn't already a paragraph being carried over, it stores the start of the paragraph's text,
            # page number and url
            if not begin_paragraph:
                begin_paragraph = BeginParagraph(source)
            # Otherwise if there is a paragraph being carried over, it just adds the text to the rest of the
            # paragraph, without changing the original page number and url
            else:
                begin_paragraph.text += source.text
            # It then breaks, exiting out of the function, so the carried paragraph is not written until all the text
            # in the paragraph has been collected

    return begin_paragraph


def irstlm_formatter(text):
    # Formats text in a way suitable for the irstlm language model
    text = re.sub(r'w[”“"\'`‘’´]', 'wh', text.lower())
    text = re.sub(r'[—–]', '-', text)
    text = re.sub(r'([^A-Za-zĀĒĪŌŪāēīōū\s])', r' \1 ', text)
    text = re.sub(r'< (date|number|time) >', r'<\1>', text)
    text = re.sub(r'-', r'@-@', text)
    return "<s> " + clean_whitespace(text) + " </s>"


def split_paragraph(source, writer, begin_paragraph):
    # This function splits the text from a given page into its constituent
    # Paragraphs, and writes them along with the page's information (date
    # Retrieved, newspaper name, issue name, page number, Maori word count,
    # Ambiguous word count, other word count, total word count, Maori word
    # Percentage, the raw text, and the url of the page). If it determines that
    # The paragraph carries on to the next page, and it is not the last page of
    # An issue, it carries the information that changes from page to page (text,
    # Page number, url) to the next time the function is called, i.e. the next
    # Page. It tries to find where the paragraph continues, and then writes it
    # To the text csv with the information of the page where it was first found.
    # If it can't, it will continue to loop this information forward until the
    # Last page of the issue. It takes a Row class object, and a csv writer.

    if source.text:  # Only writes the information if text was able to be extracted

        # Splits the text up into paragraphs
        text_list = remove_punctuations(source.text)

        # Loops through the paragraphs
        for text in text_list:

            # Strips leading and trailing white space
            source.text = text.strip()

            # If the paragraph is the last paragraph on the page
            if text == text_list[-1]:
                begin_paragraph = text_moroki(source, begin_paragraph)

            # If there is leftover text from the previous page, Find the first paragraph that isn't in caps,
            # i.e. isn't a title
            if begin_paragraph and not text.isupper():

                # Add the leftover text to the first paragraph that isn't entirely uppercase
                source.text = begin_paragraph.text + source.text
                # The page number and url that are to be written with the paragraph are from the original paragraph,
                # so they are taken from the global variable and assigned to the variables that will be written
                page_tau = begin_paragraph.page_number
                page_link = begin_paragraph.link
                # Then the global variable is cleared, because it is being written, so nothing is being carried over
                # to the next call of the function
                begin_paragraph = None

            else:
                # If nothing is being added from a previous page, the page number and url that are to be written come
                # from the current page, and are assigned to the variables which will be written
                page_tau = source.page_number
                page_link = source.link

            # Replaces all white space with a space
            source.text = clean_whitespace(source.text)
            # If there is no text left after it has been stripped, there is no point writing it, so the function
            # continues onto the next paragraph
            if not source.text:
                continue

            source.content = clean_up(source.text)
            source.content = irstlm_formatter(source.content)
            # Gets the percentage of the text that is Maori
            source.maori, source.ambiguous, source.english, source.total, source.percent = get_percentage(source.content)
            # Prepares the row that is to be written to the csv
            row = [datetime.now(), source.newspaper, source.issue, page_tau,
                       source.maori, source.ambiguous, source.english, source.total, source.percent, source.content,
                       page_link, source.text]
            # Writes the date retrieved, newspaper name, issue name, page number, Maori percentage, extracted text
            # and page url to the file
            writer.writerow(row)

    return begin_paragraph
