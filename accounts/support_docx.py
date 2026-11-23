"""Read FAQ content from DOCX without executing or extracting document assets."""
import re
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree as ET

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
HEADER = re.compile(r'^\s*([0-9٠-٩۰-۹]+)\s*[-–—.)、:]\s*[-–—]*\s*(.+)$')


class SupportDocxError(ValueError):
    pass


def _xml(archive, name):
    info = archive.getinfo(name)
    if info.file_size > 4 * 1024 * 1024:
        raise SupportDocxError('محتوى الملف أكبر من الحد المسموح.')
    data = archive.read(name)
    declarations = data.replace(b'\x00', b'').upper()
    if b'<!DOCTYPE' in declarations or b'<!ENTITY' in declarations:
        raise SupportDocxError('صيغة XML غير مدعومة.')
    return ET.fromstring(data)


def _paragraph_text(element, links):
    if element.tag == f'{{{W}}}t':
        return element.text or ''
    if element.tag in (f'{{{W}}}br', f'{{{W}}}cr'):
        return '\n'
    if element.tag == f'{{{W}}}tab':
        return ' '
    text = ''.join(_paragraph_text(child, links) for child in element)
    if element.tag == f'{{{W}}}hyperlink':
        target = links.get(element.get(f'{{{R}}}id'), '')
        if target.startswith(('https://', 'http://')) and target not in text:
            text += ' ' + target
    return text


def parse_support_docx(data):
    if len(data) > 5 * 1024 * 1024:
        raise SupportDocxError('حجم الملف يجب ألا يتجاوز 5 ميغابايت.')
    try:
        with ZipFile(BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 25 * 1024 * 1024:
                raise SupportDocxError('محتوى الملف أكبر من الحد المسموح.')
            root = _xml(archive, 'word/document.xml')
            links = {}
            if 'word/_rels/document.xml.rels' in archive.namelist():
                links = {node.get('Id'): node.get('Target', '') for node in
                         _xml(archive, 'word/_rels/document.xml.rels')}
            lines = []
            automatic = 0
            for paragraph in root.findall(f'.//{{{W}}}body//{{{W}}}p'):
                text = _paragraph_text(paragraph, links).strip()
                # Word's automatic numbering is absent from the text runs.
                numbered = paragraph.find(f'{{{W}}}pPr/{{{W}}}numPr') is not None
                if numbered and re.search(r'[؟?]\s*$', text) and not HEADER.match(text):
                    automatic += 1
                    text = f'{automatic}- {text}'
                lines.extend(text.splitlines())
    except (BadZipFile, KeyError, ET.ParseError, RuntimeError, OSError) as exc:
        raise SupportDocxError('تعذّر قراءة الملف. اختر ملف Word بصيغة .docx صالحاً.') from exc

    items, warnings, answer_lines = [], [], []
    current = None
    numbers = set()

    def finish():
        if current is None:
            return
        answer = '\n'.join(answer_lines).strip()
        if not answer:
            raise SupportDocxError(f'السؤال «{current[1]}» لا يحتوي على إجابة.')
        if len(current[1]) > 500:
            raise SupportDocxError('أحد الأسئلة يتجاوز 500 حرف.')
        if 'رابط فيديو' in answer and not re.search(r'https?://', answer):
            warnings.append(f'السؤال {len(items) + 1}: عبارة «رابط فيديو» بدون رابط فعلي.')
        items.append({'question': current[1], 'answer': answer})

    for line in lines:
        match = HEADER.match(line)
        if match:
            number, question = match.groups()
            # A numbered answer step without a question mark is not a new FAQ.
            # Missing-mark headers must look like a question as well.
            number = int(number)
            if not re.search(r'[؟?]', question) and not re.match(
                    r'^(?:كيف|لماذا|هل|أين|اين|متى|ماهي|ماذا|ما\s|شرح|ادارة|إدارة)', question):
                answer_lines.append(line.strip())
                continue
            finish()
            if number in numbers:
                warnings.append(f'الرقم {number} مكرر في الملف؛ سيُعتمد ترتيب ظهور الأسئلة.')
            numbers.add(number)
            if not re.search(r'[؟?]', question):
                warnings.append(f'السؤال {len(items) + 1}: لا توجد علامة استفهام في نهايته.')
            current = (number, question.strip())
            answer_lines = []
        elif current is not None:
            answer_lines.append(line.strip())
        elif line.strip():
            warnings.append('تم تجاهل نص قبل السؤال الأول: ' + line.strip()[:100])
    finish()
    if not items:
        raise SupportDocxError('لم يتم العثور على أسئلة مرقمة. يجب أن يلي كل سؤال نص الإجابة.')
    if len(items) > 1000:
        raise SupportDocxError('الحد الأقصى للاستيراد 1000 سؤال في الملف الواحد.')
    seen = set()
    for item in items:
        key = question_key(item['question'])
        if key in seen:
            raise SupportDocxError('يوجد سؤال مكرر بالنص داخل الملف: ' + item['question'])
        seen.add(key)
    return items, warnings


def question_key(text):
    return re.sub(r'\s+', ' ', text).strip()
