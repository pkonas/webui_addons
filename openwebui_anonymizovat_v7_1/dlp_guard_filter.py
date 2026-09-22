"""
title: DLP Guard a anonymizační jádro
version: 7.1.0
author: Reference implementation
required_open_webui_version: 0.11.3
description: Global DLP guard and deterministic Workspace Tool launcher. No cleanup, no Action, no slash command, no new-chat DOM automation.
"""
from __future__ import annotations
import asyncio
import base64
import copy
import hashlib
import hmac
import inspect
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional
from pydantic import BaseModel, Field

# No local companion modules, external services, pip requirements or source patches.

POLICY_VERSION = "postwrite-v5"  # Stable token domain only; v6 performs NO cleanup.
SUPPORTED_BACKEND_VERSIONS = {"0.11.3"}
class DLPError(RuntimeError):
    def __init__(self, code="DLP_CHECK_FAILED"):
        self.code = code
        super().__init__(code)
DLPBlocked = DLPError

def fail(code: str):
    raise DLPError(code)

LANGUAGE_NAMES = {
    'cs':'čeština', 'sk':'slovenština', 'uk':'ukrajinština', 'pl':'polština',
    'bg':'bulharština', 'hr':'chorvatština', 'sl':'slovinština', 'en':'angličtina',
    'de':'němčina', 'it':'italština', 'es':'španělština', 'ja':'japonština',
    'zh':'čínština (zjednodušená i tradiční)', 'fr':'francouzština',
}

LANGUAGES = tuple(LANGUAGE_NAMES)

LABELS = {
 'cs': {
  'PERSON': ['Jméno','Jméno a příjmení','Kontaktní osoba'],
  'ADDRESS': ['Adresa','Adresa bydliště','Bydliště'], 'DOB':['Datum narození','Narozen','Narozena'],
  'RC':['Rodné číslo','RČ'], 'ACCOUNT':['Bankovní účet','Číslo účtu'],
  'EMAIL':['E-mail','Email','E-mailová adresa'], 'PHONE':['Telefon','Telefonní číslo','Mobil'],
  'SECRET':['Heslo','API klíč','Přístupový token'], 'PASSPORT':['Číslo pasu','Číslo dokladu'],
  'TAX_ID':['Daňové identifikační číslo','DIČ'],
 },
 'sk': {
  'PERSON':['Meno','Meno a priezvisko','Kontaktná osoba'],
  'ADDRESS':['Adresa','Adresa bydliska','Bydlisko'], 'DOB':['Dátum narodenia','Narodený','Narodená'],
  'RC':['Rodné číslo','RČ'], 'ACCOUNT':['Bankový účet','Číslo účtu'],
  'EMAIL':['E-mail','Email','E-mailová adresa'], 'PHONE':['Telefón','Telefónne číslo','Mobil'],
  'SECRET':['Heslo','API kľúč','Prístupový token'], 'PASSPORT':['Číslo pasu','Číslo dokladu'],
  'TAX_ID':['Daňové identifikačné číslo','DIČ'],
 },
 'uk': {
  'PERSON':["Ім'я","Ім’я","Імʼя","Імʼя та прізвище",'Ім’я та прізвище',"Ім'я та прізвище",'Прізвище та ім’я','ПІБ','Контактна особа'],
  'ADDRESS':['Адреса','Адреса проживання'], 'DOB':['Дата народження'],
  'NATIONAL_ID':['РНОКПП','Ідентифікаційний номер','Ідентифікаційний код'],
  'ACCOUNT':['Банківський рахунок','Номер рахунку'], 'EMAIL':['Електронна пошта','Адреса електронної пошти','E-mail'],
  'PHONE':['Телефон','Номер телефону','Мобільний телефон'],
  'SECRET':['Пароль','Ключ API','Токен доступу'], 'PASSPORT':['Номер паспорта'], 'TAX_ID':['ІПН'],
 },
 'pl': {
  'PERSON':['Imię','Imię i nazwisko','Osoba kontaktowa'], 'ADDRESS':['Adres','Adres zamieszkania'],
  'DOB':['Data urodzenia'], 'NATIONAL_ID':['PESEL'], 'ACCOUNT':['Rachunek bankowy','Numer konta','Numer rachunku'],
  'EMAIL':['E-mail','Email','Adres e-mail'], 'PHONE':['Telefon','Numer telefonu','Telefon komórkowy'],
  'SECRET':['Hasło','Klucz API','Token dostępu'], 'PASSPORT':['Numer paszportu','Numer dowodu osobistego'], 'TAX_ID':['NIP'],
 },
 'bg': {
  'PERSON':['Име','Име и фамилия','Три имена','Лице за контакт'], 'ADDRESS':['Адрес','Адрес на местоживеене'],
  'DOB':['Дата на раждане'], 'NATIONAL_ID':['ЕГН','ЛНЧ'], 'ACCOUNT':['Банкова сметка','Номер на сметка'],
  'EMAIL':['Електронна поща','Имейл','E-mail'], 'PHONE':['Телефон','Телефонен номер','Мобилен телефон'],
  'SECRET':['Парола','API ключ','Ключ за API','Токен за достъп'], 'PASSPORT':['Номер на паспорт','Номер на лична карта'],
 },
 'hr': {
  'PERSON':['Ime','Ime i prezime','Kontakt osoba'], 'ADDRESS':['Adresa','Adresa prebivališta'],
  'DOB':['Datum rođenja'], 'NATIONAL_ID':['OIB','Osobni identifikacijski broj'],
  'ACCOUNT':['Bankovni račun','Broj računa'], 'EMAIL':['E-mail','Email','E-pošta','Adresa e-pošte'],
  'PHONE':['Telefon','Broj telefona','Mobitel'], 'SECRET':['Lozinka','API ključ','Pristupni token'],
  'PASSPORT':['Broj putovnice','Broj osobne iskaznice'],
 },
 'sl': {
  'PERSON':['Ime','Ime in priimek','Kontaktna oseba'], 'ADDRESS':['Naslov','Naslov prebivališča'],
  'DOB':['Datum rojstva'], 'NATIONAL_ID':['EMŠO','Enotna matična številka občana'],
  'ACCOUNT':['Bančni račun','Številka računa'], 'EMAIL':['E-pošta','Elektronska pošta','E-mail'],
  'PHONE':['Telefon','Telefonska številka','Mobilni telefon'],
  'SECRET':['Geslo','Ključ API','API ključ','Dostopni žeton'], 'PASSPORT':['Številka potnega lista'], 'TAX_ID':['Davčna številka'],
 },
 'en': {
  'PERSON':['Name','Full name','First name','Last name','Contact person','Contact name'],
  'ADDRESS':['Address','Home address','Residential address','Postal address'], 'DOB':['Date of birth','Birth date','DOB'],
  'NATIONAL_ID':['National ID','National identification number','Social security number','SSN'],
  'ACCOUNT':['Bank account','Bank account number','Account number'], 'EMAIL':['E-mail','Email','Email address'],
  'PHONE':['Phone','Phone number','Telephone','Mobile','Mobile number'],
  'SECRET':['Password','API key','API_key','API-key','Access token','Access_token','Secret key'],
  'PASSPORT':['Passport','Passport number','ID number'], 'TAX_ID':['Tax ID','Tax identification number'],
  'CARD':['Credit card','Credit card number','Card number'],
 },
 'de': {
  'PERSON':['Name','Vollständiger Name','Vorname','Nachname','Ansprechpartner','Kontaktperson'],
  'ADDRESS':['Adresse','Anschrift','Wohnanschrift','Wohnadresse'], 'DOB':['Geburtsdatum'],
  'NATIONAL_ID':['Personalausweisnummer','Sozialversicherungsnummer'],
  'ACCOUNT':['Bankkonto','Kontonummer','Bankverbindung'], 'EMAIL':['E-Mail','E-Mail-Adresse','Email'],
  'PHONE':['Telefon','Telefonnummer','Mobiltelefon','Mobilnummer'],
  'SECRET':['Passwort','API-Schlüssel','API Schlüssel','Zugriffstoken'],
  'PASSPORT':['Reisepassnummer','Passnummer'], 'TAX_ID':['Steuer-ID','Steueridentifikationsnummer','Steuernummer'],
 },
 'it': {
  'PERSON':['Nome','Cognome','Nome e cognome','Persona di contatto'],
  'ADDRESS':['Indirizzo','Indirizzo di residenza','Residenza'], 'DOB':['Data di nascita'],
  'TAX_ID':['Codice fiscale','Partita IVA'], 'NATIONAL_ID':['Numero di identificazione nazionale'],
  'ACCOUNT':['Conto bancario','Numero di conto','Numero di conto bancario'],
  'EMAIL':['E-mail','Email','Indirizzo e-mail','Posta elettronica'], 'PHONE':['Telefono','Numero di telefono','Cellulare'],
  'SECRET':['Password','Parola d’ordine','Chiave API','Token di accesso'], 'PASSPORT':['Numero di passaporto','Numero del documento'],
 },
 'es': {
  'PERSON':['Nombre','Apellidos','Nombre y apellidos','Nombre completo','Persona de contacto'],
  'ADDRESS':['Dirección','Domicilio','Dirección postal'], 'DOB':['Fecha de nacimiento'],
  'NATIONAL_ID':['DNI','NIE','Número de identificación'], 'TAX_ID':['NIF','Identificación fiscal'],
  'ACCOUNT':['Cuenta bancaria','Número de cuenta'], 'EMAIL':['Correo electrónico','E-mail','Email'],
  'PHONE':['Teléfono','Número de teléfono','Móvil'],
  'SECRET':['Contraseña','Clave API','Token de acceso'], 'PASSPORT':['Número de pasaporte'],
 },
 'ja': {
  'PERSON':['氏名','名前','姓名','お名前','担当者','担当者名','連絡担当者'],
  'ADDRESS':['住所','現住所','居住地','郵便住所'], 'DOB':['生年月日','誕生日'],
  'NATIONAL_ID':['個人番号','マイナンバー'], 'ACCOUNT':['銀行口座','口座番号','銀行口座番号'],
  'EMAIL':['メール','メールアドレス','電子メール','Eメール'], 'PHONE':['電話','電話番号','携帯電話','携帯電話番号'],
  'SECRET':['パスワード','APIキー','API キー','アクセストークン'], 'PASSPORT':['パスポート番号','旅券番号'],
 },
 'zh': {
  'PERSON':['姓名','名字','联系人','聯絡人','联络人','联系人姓名','聯絡人姓名'],
  'ADDRESS':['地址','住址','居住地址','联系地址','聯絡地址'], 'DOB':['出生日期','出生年月日','生日'],
  'NATIONAL_ID':['身份证号','身份证号码','身份證號','身份證號碼','身分證字號','居民身份证号码'],
  'ACCOUNT':['银行账户','银行账号','银行帐号','銀行帳戶','銀行帳號','帳號'],
  'EMAIL':['电子邮件','电子邮箱','邮箱','電子郵件','電子信箱','郵箱'],
  'PHONE':['电话','电话号码','手机','手机号码','電話','電話號碼','手機','手機號碼'],
  'SECRET':['密码','密碼','API密钥','API密鑰','API金鑰','访问令牌','存取權杖'],
  'PASSPORT':['护照号码','护照号','護照號碼'], 'TAX_ID':['税号','稅號'],
 },
 'fr': {
  'PERSON':['Nom','Prénom','Nom et prénom','Nom complet','Personne de contact'],
  'ADDRESS':['Adresse','Adresse postale','Adresse du domicile'], 'DOB':['Date de naissance'],
  'NATIONAL_ID':['Numéro de sécurité sociale','NIR','Numéro de carte d’identité',"Numéro de carte d'identité"],
  'ACCOUNT':['Compte bancaire','Numéro de compte','Numéro de compte bancaire'],
  'EMAIL':['E-mail','Email','Courriel','Adresse électronique','Adresse e-mail'],
  'PHONE':['Téléphone','Numéro de téléphone','Téléphone portable','Portable'],
  'SECRET':['Mot de passe','Clé API',"Jeton d'accès",'Jeton d’accès'],
  'PASSPORT':['Numéro de passeport'], 'TAX_ID':['Numéro fiscal'],
 },
}

SHARED = {'IBAN':['IBAN'], 'CARD':['PAN']}

def labels_for(languages=LANGUAGES):
    result = {kind:set(values) for kind,values in SHARED.items()}
    for language in languages:
        if language not in LABELS:
            raise ValueError('DLP_LANGUAGE_CONFIG')
        for kind, values in LABELS[language].items():
            result.setdefault(kind,set()).update(unicodedata.normalize('NFKC',v) for v in values)
    return result

def label_patterns(languages=LANGUAGES):
    patterns=[]
    for kind, labels in sorted(labels_for(languages).items()):
        alternatives='|'.join(re.escape(x) for x in sorted(labels,key=lambda x:(-len(x),x)))
        patterns.append((kind,re.compile(
            r'(?im)(?:^|[;|])[ \t]*(?:[-*]\s+)?(?:\*\*)?(?:'+alternatives+r')(?:\*\*)?[ \t]*(?::|=|\t)[ \t]*(?P<value>[^\r\n;|]+)')))
    return patterns

KINDS = {"PERSON", "ADDRESS", "DOB", "EMAIL", "PHONE", "RC", "IBAN", "ACCOUNT", "SECRET", "ORG", "URL", "DATA", "NATIONAL_ID", "PASSPORT", "TAX_ID", "CARD"}

TOKEN = re.compile(r"\[\[(?:PERSON|ADDRESS|DOB|EMAIL|PHONE|RC|IBAN|ACCOUNT|SECRET|ORG|URL|DATA|NATIONAL_ID|PASSPORT|TAX_ID|CARD)_[a-z][a-z0-9]{0,11}_[A-Z2-7]{26}\]\]")

def normalise(text: str) -> str:
    if not isinstance(text, str):
        fail("DLP_SHAPE")
    for c in text:
        category = unicodedata.category(c)
        if category in {"Cf", "Cs"} or (category == "Cc" and c not in "\n\r\t"):
            fail("DLP_OBFUSCATED")
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    # A deliberately conservative guard, NOT a claim to detect every encoding.
    if re.search(r"(?i)data:[^\s,]{0,120};base64,", text):
        fail("DLP_OBFUSCATED")
    if re.search(r"(?<![\w])(?:[A-Za-z0-9+/]{100,}={0,2})(?![\w])", text):
        fail("DLP_OBFUSCATED")
    return text

def canonical(kind: str, value: str, default_phone_country: str = "") -> str:
    value = normalise(value).strip()
    if kind == "EMAIL":
        local, sep, domain = value.rpartition("@")
        if not sep: return value
        return local + "@" + domain.casefold()  # Local part may be case-sensitive.
    if kind == "PHONE":
        digits = re.sub(r"\D", "", value)
        if value.startswith("00"):
            digits = digits[2:]
        international = value.startswith(("+", "00"))
        if not international:
            # Region is an administrator choice, never guessed from UI/document language.
            if default_phone_country:
                digits = default_phone_country + (digits[1:] if digits.startswith("0") else digits)
            else:
                return "local:" + digits
        return "+" + digits
    if kind == "ACCOUNT":
        compact = re.sub(r"\s", "", value)
        match = re.fullmatch(r"(?:(\d{1,6})-)?(\d{1,10})/(\d{4})", compact)
        if match:
            prefix, account, bank = match.groups()
            return f"{int(prefix or '0'):06d}-{int(account):010d}/{bank}"
        return compact  # Never merge an account prefix with its account number.
    if kind in {"RC", "IBAN", "NATIONAL_ID", "PASSPORT", "TAX_ID", "CARD"}:
        return re.sub(r"[\s/.-]", "", value).upper()
    if kind == "DOB":
        m = re.fullmatch(r"(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{4})", value)
        if m:
            d, mo, y = m.groups()
            return f"{y}-{int(mo):02d}-{int(d):02d}"
    if kind in {"PERSON", "ADDRESS", "ORG"}:
        return " ".join(value.split()).casefold()
    return value

@dataclass(frozen=True)
class Span:
    start: int
    end: int
    kind: str
    value: str
    priority: int

@dataclass(frozen=True)
class Settings:
    tenant: str
    key_id: str
    aliases: tuple[dict, ...] = ()
    file_grants: dict = field(default_factory=dict)
    languages: tuple[str, ...] = LANGUAGES
    default_phone_country: str = "420"

    @staticmethod
    def from_dict(data: dict) -> "Settings":
        required = {"schema", "tenant", "key_id", "aliases", "file_grants"}
        optional = {"languages", "default_phone_country"}
        if not isinstance(data, dict) or not required <= set(data) or set(data) - required - optional:
            fail("DLP_CONFIG")
        if data["schema"] != 1 or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", data["tenant"]):
            fail("DLP_CONFIG")
        if not re.fullmatch(r"[a-z][a-z0-9]{0,11}", data["key_id"]):
            fail("DLP_CONFIG")
        if not isinstance(data["aliases"], list) or len(data["aliases"]) > 500:
            fail("DLP_CONFIG")
        for row in data["aliases"]:
            if not isinstance(row, dict) or set(row) != {"kind", "canonical", "aliases"}:
                fail("DLP_CONFIG")
            if row["kind"] not in KINDS or not isinstance(row["canonical"], str) or not row["canonical"]:
                fail("DLP_CONFIG")
            if not isinstance(row["aliases"], list) or not row["aliases"] or len(row["aliases"]) > 30:
                fail("DLP_CONFIG")
            if any(not isinstance(v, str) or not 2 <= len(v) <= 300 for v in row["aliases"]):
                fail("DLP_CONFIG")
        grants = data["file_grants"]
        if not isinstance(grants, dict) or len(grants) > 10000:
            fail("DLP_CONFIG")
        for fid, grant in grants.items():
            if not isinstance(fid, str) or not isinstance(grant, dict):
                fail("DLP_CONFIG")
            if set(grant) != {"user_id", "sha256", "allow_transform"}:
                fail("DLP_CONFIG")
            if not isinstance(grant["user_id"], str) or not re.fullmatch(r"[a-f0-9]{64}", grant["sha256"]):
                fail("DLP_CONFIG")
            if type(grant["allow_transform"]) is not bool:
                fail("DLP_CONFIG")
        languages = data.get("languages", list(LANGUAGES))
        country = data.get("default_phone_country", "420")
        if (not isinstance(languages, list) or not languages or
            any(x not in LANGUAGES for x in languages) or len(set(languages)) != len(languages) or
            not isinstance(country, str) or not re.fullmatch(r"[1-9][0-9]{0,2}|", country)):
            fail("DLP_CONFIG")
        return Settings(data["tenant"], data["key_id"], tuple(data["aliases"]), grants, tuple(languages), country)

PATTERNS = [
    ("SECRET", 0, re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("SECRET", 1, re.compile(r"(?i)\bBearer[ \t]+(?P<value>[A-Za-z0-9._~+/-]{8,}=*)")),
    ("SECRET", 1, re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16})\b")),
    ("URL", 2, re.compile(r"https?://[^\s<>\"']+", re.I)),
    ("EMAIL", 3, re.compile(r"(?<![\w.!#$%&'*+/=?^`{|}~-])[\w.!#$%&'*+/=?^`{|}~-]+@(?:[\w-]+\.)+[\w-]{2,63}(?![\w-])")),
    ("IBAN", 4, re.compile(r"(?<!\w)(?:CZ|SK)(?:[ \t]?\d){22}(?![ \t]?\d)", re.I)),
    ("RC", 5, re.compile(r"(?<!\d)(?:\d{6}[ \t]*/[ \t]*\d{3,4}|\d{10})(?!\d)")),
    ("ACCOUNT", 6, re.compile(r"(?<![\w/])(?:\d{1,6}-)?\d{2,10}/\d{4}(?!\d)")),
    ("PHONE", 7, re.compile(r"(?<![\w+])(?:(?:\+|00)(?:420|421)[ \t.-]*)?[2-9]\d{2}[ \t.-]*\d{3}[ \t.-]*\d{3}(?!\w)")),
]

PATTERNS.extend([
    ("PHONE", 3, re.compile(r"(?<![\w+])(?:\+|00)[1-9](?:[ \t().-]?[0-9]){6,14}(?![0-9])")),
    ("IBAN", 3, re.compile(r"(?<!\w)[A-Z]{2}[0-9]{2}(?:[ \t]?[A-Z0-9]){11,30}(?![A-Z0-9])")),
    # Conservative long-number candidate, not a claim of country/checksum validity.
    ("NATIONAL_ID", 8, re.compile(r"(?<![\w-])(?:[0-9][ \t]?){10,18}[0-9Xx](?![\w-])")),
])

LABEL_PATTERNS = label_patterns()

class Engine:
    """Per-request state only. No global alias table or persistent reverse mapping."""
    def __init__(self, settings: Settings, key: bytes, user_id: str, max_chars: int = 120_000):
        if len(key) != 32:
            fail("DLP_CONFIG")
        self.settings = settings
        self.key = key
        self.user_id = user_id
        self.max_chars = max_chars
        self.label_patterns = label_patterns(settings.languages)
        self.aliases: dict[str, tuple[str, str, str, int]] = {}
        self.compiled_aliases: list[tuple[re.Pattern, str, str, int]] = []
        for row in settings.aliases:
            for variant in row["aliases"]:
                self._add_alias(variant, row["kind"], self.canonical(row["kind"], row["canonical"]), 0, strict=True)
        self._compile_aliases()

    def canonical(self, kind: str, value: str) -> str:
        return canonical(kind, value, self.settings.default_phone_country)

    def _add_alias(self, variant: str, kind: str, value: str, priority: int, *, strict: bool = False) -> None:
        variant = normalise(variant).strip()
        index = " ".join(variant.split()).casefold()
        old = self.aliases.get(index)
        if old:
            if (old[1], old[2]) != (kind, value):
                if strict:
                    fail("DLP_CONFIG")
                if old[3] == priority:
                    # Ambiguous labels fail identically regardless of source ordering.
                    fail("DLP_UNSUPPORTED")
            return
        if len(self.aliases) >= 15000:
            fail("DLP_LIMIT")
        self.aliases[index] = (variant, kind, value, priority)

    def _compile_aliases(self) -> None:
        compiled = []
        for _, (variant, kind, value, priority) in sorted(self.aliases.items()):
            parts = re.split(r"\s+", variant)
            expr = r"[ \t]+".join(re.escape(p) for p in parts)
            # Aliases are literal data, not executable regular expressions.
            # CJK entities need no whitespace/word boundary in ordinary sentences.
            cjk = any("\u3040" <= c <= "\u9fff" for c in variant)
            compiled.append((re.compile(expr if cjk else r"(?<!\w)" + expr + r"(?!\w)", re.I), kind, value, priority))
        self.compiled_aliases = compiled

    def learn(self, texts: list[str]) -> None:
        """Learn labelled values from ALL messages/files before sanitising any of them."""
        if sum(len(t) for t in texts) > self.max_chars:
            fail("DLP_LIMIT")
        for source in texts:
            text = normalise(source)
            for kind, pattern in self.label_patterns:
                for m in pattern.finditer(text):
                    value = m.group("value").strip()
                    if not value or TOKEN.fullmatch(value):
                        continue
                    # A mixed value containing a token is unsupported, not trusted.
                    if TOKEN.search(value):
                        fail("DLP_UNSUPPORTED")
                    if len(value) > 300:
                        fail("DLP_LIMIT")
                    self._add_alias(value, kind, self.canonical(kind, value), 1)
        self._compile_aliases()

    def token(self, kind: str, value: str) -> str:
        # Length-delimited JSON avoids ambiguous concatenation/domain separation.
        message = json.dumps(
            ["owui-dlp/v1", POLICY_VERSION, self.settings.tenant, self.user_id, kind, value],
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        digest = hmac.new(self.key, message, hashlib.sha256).digest()[:16]
        encoded = base64.b32encode(digest).decode("ascii").rstrip("=")
        return f"[[{kind}_{self.settings.key_id}_{encoded}]]"

    def spans(self, source: str) -> tuple[str, list[Span]]:
        text = normalise(source)
        if len(text) > self.max_chars:
            fail("DLP_LIMIT")
        protected = [(m.start(), m.end()) for m in TOKEN.finditer(text)]
        found: list[Span] = []

        def add(start: int, end: int, kind: str, value: str, priority: int) -> None:
            if any(a <= start and end <= b for a, b in protected):
                return
            found.append(Span(start, end, kind, value, priority))
            if len(found) > 25000:
                fail("DLP_LIMIT")

        for kind, priority, pattern in PATTERNS:
            for m in pattern.finditer(text):
                group = "value" if "value" in m.re.groupindex else 0
                add(m.start(group), m.end(group), kind, self.canonical(kind, m.group(group)), priority + 10)
        for kind, pattern in self.label_patterns:
            for m in pattern.finditer(text):
                value = m.group("value").strip()
                if value and not TOKEN.fullmatch(value):
                    if TOKEN.search(value):
                        fail("DLP_UNSUPPORTED")
                    start = m.start("value") + len(m.group("value")) - len(m.group("value").lstrip())
                    add(start, start + len(value), kind, self.canonical(kind, value), 1)
        for pattern, kind, value, priority in self.compiled_aliases:
            for m in pattern.finditer(text):
                add(m.start(), m.end(), kind, value, priority)

        # Union of intersecting spans: never leave a suffix of a crossing entity raw.
        merged = []
        found.sort(key=lambda s: (s.start, -s.end, s.priority, s.kind, s.value))
        index = 0
        while index < len(found):
            cluster = [found[index]]
            start, end = found[index].start, found[index].end
            index += 1
            while index < len(found) and found[index].start < end:
                cluster.append(found[index])
                end = max(end, found[index].end)
                index += 1
            covers = [s for s in cluster if s.start == start and s.end == end]
            if covers:
                merged.append(min(covers, key=lambda s: (s.priority, s.kind, s.value)))
            else:
                merged.append(Span(start, end, "DATA", text[start:end], 99))
        return text, merged

    def sanitise(self, source: str) -> tuple[str, dict[str, int]]:
        text, spans = self.spans(source)
        if not spans:
            return source, {}
        result = []
        position = 0
        counts: Counter = Counter()
        for span in spans:
            result.extend([text[position:span.start], self.token(span.kind, span.value)])
            counts[span.kind] += 1
            position = span.end
        result.append(text[position:])
        output = "".join(result)
        if self.spans(output)[1]:
            fail("DLP_RECHECK")
        return output, dict(sorted(counts.items()))



import io
import csv
import zipfile
from pathlib import Path
from types import SimpleNamespace
from email import policy as email_policy
from email.parser import BytesParser
from html.parser import HTMLParser
import secrets

API_VERSION = "dlp-workspace/7.1"
REQUEST_MARKER = "_dlp_guard_v71_checked"
DIALOG_INPUT = "_dlp_v71_input"
DIALOG_CALL = "_dlp_v71_tool_invocation"

class GuardValves(BaseModel):
    priority: int = 10000
    hmac_key: str = Field(default="", description="Pouze správce. Náhodný tajný řetězec min. 32 znaků pro dialog; nikdy se neposílá prohlížeči.", json_schema_extra={"input": {"type": "password"}})
    tenant: str = "default"
    key_id: str = "k1"
    aliases_json: str = "[]"
    default_phone_country: str = ""
    anonymizer_tool_id: str = Field(default="anonymizovat", description="Skutečné ID Workspace Tool Anonymizovat, nikoli Action Function.")
    max_chars: int = Field(default=400000, ge=1000, le=1000000)
    max_file_bytes: int = Field(default=5000000, ge=1024, le=20000000)
    max_total_bytes: int = Field(default=10000000, ge=1024, le=30000000)
    max_files: int = Field(default=5, ge=1, le=10)
    max_members: int = Field(default=500, ge=1, le=1000)
    max_pages: int = Field(default=100, ge=1, le=200)
    operation_timeout: int = Field(default=45, ge=5, le=180)

    def engine(self, uid: str, *, masking: bool = False) -> Engine:
        if not uid:
            fail("DLP_AUTH")
        if masking and len(self.hmac_key) < 32:
            fail("DLP_HMAC_KEY_REQUIRED")
        try:
            cfg = Settings.from_dict({"schema": 1, "tenant": self.tenant,
                "key_id": self.key_id, "aliases": json.loads(self.aliases_json),
                "file_grants": {}, "languages": list(LANGUAGES),
                "default_phone_country": self.default_phone_country})
            # Dummy key is only for blocking detection. Masking refuses an absent key.
            key = hashlib.sha256(self.hmac_key.encode("utf-8")).digest()
            return Engine(cfg, key, uid, self.max_chars)
        except DLPError:
            raise
        except Exception:
            fail("DLP_CONFIG")

def flattened(value: Any, depth=0):
    if depth > 32:
        raise DLPError('DLP_DEPTH')
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for child in value:
            yield from flattened(child, depth + 1)
    elif isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise DLPError('DLP_JSON')
            # Also construct labelled views of fields such as {"氏名": "山田花子"}.
            if isinstance(child, (str, int, float)) and not isinstance(child, bool):
                yield f'{key}: {child}'
            yield from flattened(child, depth + 1)


class _Html(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text=[]
    def handle_data(self, data):
        self.text.append(data)
    def handle_starttag(self, tag, attrs):
        if tag in {'img', 'video', 'audio', 'iframe', 'object', 'embed'}:
            raise DLPError('DLP_MEDIA_UNINSPECTABLE')
        for k,v in attrs:
            if v and k in {'href','src','title','alt','value','data','content'}:
                self.text.append(v)


def decode_text(data: bytes) -> str:
    try:
        if data.startswith((b'\xff\xfe\x00\x00', b'\x00\x00\xfe\xff')):
            return data.decode('utf-32')
        if data.startswith((b'\xff\xfe', b'\xfe\xff')):
            return data.decode('utf-16')
        text = data.decode('utf-8-sig')
        normalise(text)
        return text
    except (UnicodeError, DLPBlocked):
        raise DLPError('DLP_BINARY_OR_ENCODING') from None


def extract_document(data: bytes, name: str, cfg: GuardValves, depth=0) -> str:
    """Lossy all-text projection; rejecting a format is NOT a clean result.

    No OCR/ASR, subprocess, HTTP call, or writes of raw bytes. Complex parsers run
    in a bounded caller thread, not a security sandbox. A timeout cannot kill a
    running Python thread. Byte/structure limits are NOT full parser isolation.
    """
    if depth > 4 or len(data) > cfg.max_file_bytes:
        raise DLPError('DLP_FILE_LIMIT')
    suffix = Path(name).suffix.casefold()
    if data.lstrip().startswith(b'{\\rtf'):
        raise DLPError('DLP_RTF_UNINSPECTABLE')
    if data.startswith(b'%PDF-'):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data), strict=True)
            if reader.is_encrypted or len(reader.pages)>cfg.max_pages:
                raise DLPError('DLP_PDF_ENCRYPTED_OR_LIMIT')
            root=reader.trailer['/Root']
            if any(k in root for k in ('/AA','/AcroForm')):
                raise DLPError('DLP_PDF_ACTIVE_OR_FORM')
            action = root.get('/OpenAction')
            if hasattr(action, 'get_object'): action = action.get_object()
            # A page destination array is navigation, not executable PDF code.
            if action is not None and not isinstance(action, (list, tuple)):
                raise DLPError('DLP_PDF_ACTIVE_OR_FORM')
            names = root.get('/Names', {})
            if hasattr(names, 'get_object'): names=names.get_object()
            if any(k in names for k in ('/EmbeddedFiles','/JavaScript')):
                raise DLPError('DLP_PDF_EMBEDDED')
            parts=[]
            for p in reader.pages:
                if p.get('/Annots') or p.get('/AA'):
                    raise DLPError('DLP_PDF_IMAGE_OR_ANNOTATION')
                if len(p.images):
                    if not getattr(cfg, 'text_projection', False):
                        raise DLPError('DLP_PDF_IMAGE_OR_ANNOTATION')
                    parts.append('[Obrazová část vynechána; není předávána modelu.]')
                t=p.extract_text() or ''
                if not t.strip():
                    raise DLPError('DLP_PDF_NO_TEXT')
                parts.append(t)
            for k,v in (reader.metadata or {}).items():
                if v:
                    parts.append(('Full name: ' if str(k) in {'/Author'} else str(k)+': ') + str(v))
            result='\n'.join(parts)
        except DLPError:
            raise
        except Exception:
            raise DLPError('DLP_PDF_PARSER') from None
    elif data.startswith(b'PK'):
        try:
            from defusedxml import ElementTree as ET
            parts=[]; expanded=0
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                members=z.infolist()
                if len(members)>cfg.max_members:
                    raise DLPError('DLP_ZIP_LIMIT')
                seen=set()
                for member in members:
                    if member.is_dir(): continue
                    if member.filename in seen or member.flag_bits & 1:
                        raise DLPError('DLP_ZIP_UNSAFE')
                    seen.add(member.filename)
                    if member.file_size>cfg.max_file_bytes or member.file_size>200*max(1,member.compress_size):
                        raise DLPError('DLP_ZIP_LIMIT')
                    expanded+=member.file_size
                    if expanded>cfg.max_file_bytes*3:
                        raise DLPError('DLP_ZIP_LIMIT')
                    b=z.read(member)
                    ext=Path(member.filename).suffix.casefold()
                    if ext in {'.xml','.rels','.opf','.ncx'}:
                        tree=ET.fromstring(b)
                        for paragraph in tree.iter():
                            local_p=paragraph.tag.rsplit('}',1)[-1]
                            if local_p=='p':
                                # Element text alone avoids serialised tags/namespace URLs.
                                joined=''.join(paragraph.itertext()).strip()
                                if joined: parts.append(joined)
                            if local_p in {'tr','table-row'}:
                                cells=[]
                                for cell in paragraph:
                                    if cell.tag.rsplit('}',1)[-1] in {'tc','table-cell'}:
                                        cells.append(''.join(cell.itertext()).strip())
                                if len(cells)==2 and cells[0] and cells[1]:
                                    parts.append(cells[0].rstrip(':')+': '+cells[1])
                        for node in tree.iter():
                            local=node.tag.rsplit('}',1)[-1].lower()
                            if local in {'object','oleobject','embeddedobject','binary-data'}:
                                raise DLPError('DLP_EMBEDDED_OBJECT')
                            if node.text and node.text.strip():
                                parts.append(('Full name: ' if local in {'creator','lastmodifiedby'} else '')+node.text)
                            if node.tail and node.tail.strip(): parts.append(node.tail)
                            for k,v in node.attrib.items():
                                k=k.rsplit('}',1)[-1].lower()
                                if k in {'href','target','author','name','val'} and v:
                                    if k=='target' and node.attrib.get('TargetMode')!='External': continue
                                    if k=='val' and re.fullmatch(r'[A-Za-z0-9_-]{1,40}', v): continue
                                    parts.append(('Full name: ' if k=='author' else '')+v)
                    elif member.filename in {'mimetype'}:
                        continue
                    elif ext in {'.png','.jpg','.jpeg','.gif','.webp','.bmp','.tif','.tiff','.emf','.wmf'} and getattr(cfg, 'text_projection', False):
                        parts.append('[Obrazová část vynechána; není předávána modelu.]')
                    else:
                        parts.append(extract_document(b,member.filename,cfg,depth+1))
            result='\n'.join(parts)
        except DLPError:
            raise
        except Exception:
            raise DLPError('DLP_ZIP_OR_XML') from None
    elif suffix in {'.eml'}:
        try:
            mail=BytesParser(policy=email_policy.default).parsebytes(data)
            if mail.defects: raise DLPError('DLP_MAIL_DEFECT')
            parts=[f'{k}: {v}' for k,v in mail.items()]
            for part in mail.walk():
                if part.is_multipart(): continue
                b=part.get_payload(decode=True) or b''
                partname=part.get_filename() or ('body.html' if part.get_content_type()=='text/html' else 'body.txt')
                if part.get_content_maintype() not in {'text','application'}:
                    raise DLPError('DLP_MAIL_MEDIA')
                parts.append(extract_document(b,partname,cfg,depth+1))
            result='\n'.join(parts)
        except DLPError: raise
        except Exception: raise DLPError('DLP_MAIL_PARSER') from None
    elif suffix in {'.html','.htm','.xhtml'}:
        parser=_Html(); parser.feed(decode_text(data)); result='\n'.join(parser.text)
    elif suffix in {'.xml','.svg'}:
        if suffix=='.svg': raise DLPError('DLP_VECTOR_IMAGE')
        try:
            from defusedxml import ElementTree as ET
            tree=ET.fromstring(data)
            parts=[]
            for node in tree.iter():
                local=node.tag.rsplit('}',1)[-1]
                if node.text: parts.append(f'{local}: {node.text}')
                parts.extend(f'{k}: {v}' for k,v in node.attrib.items())
            result='\n'.join(parts)
        except Exception: raise DLPError('DLP_XML_PARSER') from None
    else:
        text=decode_text(data)
        if suffix in {'.json','.jsonl','.ndjson'}:
            try:
                values=[json.loads(line) for line in text.splitlines() if line.strip()] if suffix!='.json' else [json.loads(text)]
                result='\n'.join(t for v in values for t in flattened(v))
            except Exception: raise DLPError('DLP_JSON_PARSER') from None
        elif suffix in {'.csv','.tsv'}:
            rows=list(csv.reader(io.StringIO(text), delimiter='\t' if suffix=='.tsv' else ','))
            parts=[text]
            if rows:
                for row in rows[1:]:
                    parts.extend(f'{k}: {v}' for k,v in zip(rows[0],row))
            result='\n'.join(parts)
        elif suffix in {'.rtf','.pdf','.doc','.xls','.ppt','.msg','.png','.jpg','.jpeg','.gif','.webp','.mp3','.mp4','.wav','.7z','.rar'}:
            raise DLPError('DLP_FORMAT_UNINSPECTABLE')
        else:
            result=text
    if len(result)>cfg.max_chars or not result.strip():
        raise DLPError('DLP_EMPTY_OR_LIMIT')
    return result


LAUNCH_HELP = (
    "Zapněte Workspace Tool Anonymizovat a odešlete zadání znovu; "
    "verze 7.1 otevře dialog i pro citlivý text. Očištěný náhled musíte schválit. "
    "Pro nové originály bez běžného uploadu odešlete jen Otevřít anonymizátor "
    "a vložte je až do dialogu. "
)
WARNING = (
    "Byly rozpoznány citlivé údaje v zadání, historii nebo příloze. Zpracování LLM bylo zastaveno. "
    + LAUNCH_HELP + "Již odeslané originály mohou zůstat v historii a úložišti. "
    "Doporučujeme odstranit citlivé vlákno a původní uploady. Filtr nic automaticky nemaže."
)
UNINSPECTABLE = (
    "Obsah nelze v tomto profilu zkontrolovat; nejde o potvrzený nález citlivých údajů. "
    "Zpracování LLM bylo preventivně zastaveno. " + LAUNCH_HELP
)
# Only these exact, harmless commands open an empty editor. Arbitrary text is preserved.
EMPTY_LAUNCHERS = {"otevřít anonymizátor", "otevřít anonymizátor.", "/anonymizovat"}


def selected_workspace_tools(body: dict, metadata: dict) -> set[str]:
    """Read explicit chat selection, including the metadata moved by WebUI.

    This is an activation hint, NEVER an authorisation. The normal get_tools()
    access-control checks must still run before executing a selected tool.
    """
    result = set()
    for obj in (body, body.get('metadata', {}), metadata):
        if not isinstance(obj, dict):
            continue
        values = obj.get('tool_ids')
        if values is None:
            continue
        if not isinstance(values, list) or len(values) > 100 or any(not isinstance(x, str) for x in values):
            fail('DLP_TOOL_SELECTION')
        result.update(values)
    return result


async def invoke_workspace_anonymizer(request, tool_id: str, uid: str, user: dict,
                                      metadata: dict, emitter, caller, pending: dict) -> dict:
    """Use WebUI's existing tool resolver; do not bypass owner/group grants."""
    if not callable(caller):
        fail('DLP_BROWSER_CONNECTION_REQUIRED')
    from open_webui.models.users import Users
    from open_webui.utils.tools import get_tools
    resolved_user = await Users.get_user_by_id(uid)
    if not resolved_user or resolved_user.id != uid or resolved_user.role not in {'admin', 'user'}:
        fail('DLP_AUTH')
    tools = await get_tools(request, [tool_id], resolved_user, {
        '__request__': request, '__user__': user,
        '__event_emitter__': emitter, '__event_call__': caller,
        '__metadata__': metadata, '__messages__': [], '__files__': [],
        '__chat_id__': metadata.get('chat_id'),
        '__message_id__': metadata.get('message_id'),
    })
    if not isinstance(tools, dict):
        fail('DLP_TOOL_UNAVAILABLE')
    candidates = [v for v in tools.values() if isinstance(v, dict) and
                  v.get('tool_id') == tool_id and v.get('spec', {}).get('name') == 'anonymizovat']
    if len(candidates) != 1 or not callable(candidates[0].get('callable')):
        fail('DLP_TOOL_UNAVAILABLE')
    # The public tool takes no model-generated raw text or file arguments.
    setattr(request.state, DIALOG_CALL, (uid, tool_id))
    setattr(request.state, DIALOG_INPUT, pending)
    try:
        response = await candidates[0]['callable']()
    finally:
        for attr in (DIALOG_CALL, DIALOG_INPUT):
            if hasattr(request.state, attr):
                delattr(request.state, attr)
    if not isinstance(response, dict) or response.get('protocol') != API_VERSION:
        fail('DLP_TOOL_PROTOCOL')
    if response.get('status') != 'approved':
        code = response.get('code', 'DLP_CANCELLED')
        fail(code if isinstance(code, str) and re.fullmatch(r'DLP_[A-Z_]{1,60}', code) else 'DLP_TOOL_FAILED')
    return response

MODEL_FIELDS = {'model','messages','stream','stream_options','temperature','top_p','top_k',
    'min_p','max_tokens','max_completion_tokens','seed','stop','frequency_penalty',
    'presence_penalty','repetition_penalty','repeat_penalty','logit_bias','logprobs',
    'top_logprobs','n','response_format','reasoning_effort','verbosity','store','options','keep_alive'}
UI_FIELDS = {'metadata','files','features','background_tasks','params','variables','id','chat_id',
    'session_id','filter_ids','tool_ids','tool_servers','tools','tool_choice','skill_ids',
    'terminal_id','folder_id','model_item','user'}


def verify_backend() -> None:
    from open_webui.env import VERSION
    if str(VERSION) not in SUPPORTED_BACKEND_VERSIONS:
        fail('DLP_VERSION')


def verified_uid(user: dict) -> str:
    if (not isinstance(user, dict) or user.get('role') not in {'user','admin'} or
        not isinstance(user.get('id'), str) or not user['id']):
        fail('DLP_AUTH')
    return user['id']


def content_texts(value: Any, depth: int = 0) -> list[str]:
    if depth > 24:
        fail('DLP_DEPTH')
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [t for v in value for t in content_texts(v, depth + 1)]
    if isinstance(value, dict):
        return [t for k, v in value.items() for t in ([str(k)] + content_texts(v, depth + 1))]
    if value is None or isinstance(value, (bool, int, float)):
        return []
    fail('DLP_SHAPE')


def validated_messages(body: dict) -> list[dict]:
    messages = body.get('messages')
    if not isinstance(messages, list) or not messages:
        fail('DLP_MESSAGES')
    result = []
    for source in messages:
        if not isinstance(source, dict) or source.get('role') not in {'user','assistant','system','developer','tool'}:
            fail('DLP_MESSAGE_SHAPE')
        content = source.get('content', '')
        if isinstance(content, list):
            if any(not isinstance(p, dict) or p.get('type') not in {'text','input_text','output_text'} or
                   not isinstance(p.get('text'), str) for p in content):
                fail('DLP_NON_TEXT')
            content = '\n'.join(p['text'] for p in content)
        if not isinstance(content, str):
            fail('DLP_NON_TEXT')
        if source.get('tool_calls') or source.get('function_call'):
            fail('DLP_TOOL_PAYLOAD')
        # Retain IDs needed by WebUI, but do not forward original attachment carriers.
        row = {k: copy.deepcopy(v) for k, v in source.items()
               if k in {'role','id','name','tool_call_id'}}
        row['content'] = content
        result.append(row)
    return result


def attachment_ids(body: dict, metadata: dict) -> list[str]:
    ids = set()
    sources = [body.get('files'), metadata.get('files')]
    if isinstance(body.get('metadata'), dict):
        sources.append(body['metadata'].get('files'))
    sources += [m.get('files') for m in body.get('messages', []) if isinstance(m, dict)]
    for items in sources:
        if items is None:
            continue
        if not isinstance(items, list):
            fail('DLP_FILE_REFERENCE')
        for item in items:
            if not isinstance(item, dict) or item.get('type') in {'image','audio','video','collection'} or item.get('collection_names'):
                fail('DLP_FILE_REFERENCE')
            nested = item.get('file') if isinstance(item.get('file'), dict) else {}
            fid = item.get('id') or item.get('file_id') or nested.get('id')
            if not isinstance(fid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', fid):
                fail('DLP_FILE_REFERENCE')
            ids.add(fid)
    return sorted(ids)


class Filter:
    Valves = GuardValves
    api_version = API_VERSION

    def __init__(self):
        self.valves = self.Valves()
        self.file_handler = True
        self.toggle = False

    async def _read_uploaded_file(self, fid: str, uid: str) -> tuple[str, bytes]:
        # Read-only operations only. No delete, update, upload, event worker or scheduler.
        from open_webui.models.files import Files
        from open_webui.storage.provider import Storage
        record = await Files.get_file_by_id(fid)
        if record is None or record.user_id != uid or not record.path:
            fail('DLP_FILE_ACCESS')
        def read():
            resolved = Storage.get_file(record.path)
            with open(resolved, 'rb') as stream:
                data = stream.read(self.valves.max_file_bytes + 1)
            if len(data) > self.valves.max_file_bytes:
                fail('DLP_FILE_LIMIT')
            return str(record.filename), data
        return await asyncio.to_thread(read)

    def _analyse(self, values: list[str], uid: str) -> tuple[Engine, dict]:
        engine = self.valves.engine(uid)
        engine.learn(values)
        counts = Counter()
        for value in values:
            _, spans = engine.spans(value)
            counts.update(s.kind for s in spans)
        return engine, dict(counts)

    def anonymize_payload(self, text: str, files: list[tuple[str, bytes]], uid: str) -> dict:
        """Used exclusively by the explicit Workspace Tool dialog; never by a background event.

        Raw values stay in the caller's memory. File bytes are not sent to the upload
        endpoint. Only the returned textual projection can enter the normal chat.
        """
        cfg = self.valves
        if not isinstance(text, str) or len(text) > cfg.max_chars or len(files) > cfg.max_files:
            fail('DLP_LIMIT')
        if sum(len(b) for _, b in files) > cfg.max_total_bytes:
            fail('DLP_FILE_LIMIT')
        engine = cfg.engine(uid, masking=True)
        projections = []
        names = []
        for name, data in files:
            if not isinstance(name, str) or not isinstance(data, bytes) or len(name) > 512:
                fail('DLP_SHAPE')
            projection_cfg = SimpleNamespace(**cfg.model_dump(), text_projection=True)
            projections.append(extract_document(data, name, projection_cfg))
            names.append(name)
        values = [text] + projections + names
        engine.learn(values)
        counts = Counter()
        clean_text, hits = engine.sanitise(text)
        counts.update(hits)
        output = [clean_text.strip()] if clean_text.strip() else []
        for index, source in enumerate(projections, 1):
            projected, hits = engine.sanitise(source)
            counts.update(hits)
            output.append(f'\n--- Příloha {index}: očištěná textová reprezentace ---\n{projected}')
        # Original filenames and metadata never label the submitted attachments.
        for name in names:
            counts.update(s.kind for s in engine.spans(name)[1])
        combined = '\n\n'.join(output).strip()
        if not combined or len(combined) > cfg.max_chars:
            fail('DLP_OUTPUT_LIMIT')
        if engine.spans(combined)[1]:
            fail('DLP_RECHECK')
        # Fresh detector also catches reassembly effects and newly introduced labels.
        _, remaining = self._analyse([combined], uid)
        if remaining:
            fail('DLP_RECHECK')
        return {'text': combined, 'counts': dict(sorted(counts.items())), 'file_count': len(files)}

    def prepare_dialog_input(self, body: dict, metadata: dict, uid: str) -> dict:
        """Structural validation only: PII detection MUST NOT precede this dialog.

        The returned object is request-local, not a tool argument, DB record or
        client-supplied authorisation. Files are loaded only after explicit consent.
        """
        self.valves.engine(uid, masking=True)
        if not isinstance(body, dict) or set(body) - MODEL_FIELDS - UI_FIELDS:
            fail('DLP_REQUEST_SHAPE')
        messages = validated_messages(body)
        if messages[-1]['role'] != 'user':
            fail('DLP_MESSAGES')
        ids = attachment_ids(body, metadata)
        if len(ids) > self.valves.max_files:
            fail('DLP_FILE_LIMIT')
        if sum(len(m['content']) + len(str(m.get('name', ''))) for m in messages) > self.valves.max_chars:
            fail('DLP_LIMIT')
        text = messages[-1]['content']
        if text.strip().casefold() in EMPTY_LAUNCHERS:
            text = ''
        return {'protocol': API_VERSION, 'messages': messages, 'file_ids': ids,
                'initial_text': text,
                'config_fingerprint': hashlib.sha256(self.valves.model_dump_json().encode()).hexdigest()}

    def anonymize_request(self, messages: list[dict], text: str,
                          files: list[tuple[str, bytes]], uid: str) -> dict:
        """Sanitise ALL outgoing message content and attachment projections together.

        History in the database is NOT modified. One engine learns across all
        sources, so aliases discovered in a file apply to earlier message text too.
        """
        cfg = self.valves
        rows = validated_messages({'messages': messages})
        if not rows or rows[-1]['role'] != 'user' or not isinstance(text, str):
            fail('DLP_MESSAGES')
        if len(files) > cfg.max_files or sum(len(b) for _, b in files) > cfg.max_total_bytes:
            fail('DLP_FILE_LIMIT')
        rows[-1]['content'] = text
        names, projections = [], []
        projection_cfg = SimpleNamespace(**cfg.model_dump(), text_projection=True)
        for name, data in files:
            if not isinstance(name, str) or len(name) > 512 or not isinstance(data, bytes):
                fail('DLP_SHAPE')
            if not data or len(data) > cfg.max_file_bytes:
                fail('DLP_FILE_LIMIT')
            names.append(name)
            projections.append(extract_document(data, name, projection_cfg))
        values = [m['content'] for m in rows] + [str(m['name']) for m in rows if m.get('name')]
        engine = cfg.engine(uid, masking=True)
        engine.learn(values + projections + names)
        counts = Counter()
        for row in rows:
            row['content'], hits = engine.sanitise(row['content'])
            counts.update(hits)
            if row.get('name'):
                row['name'], hits = engine.sanitise(str(row['name']))
                counts.update(hits)
        last = [rows[-1]['content'].strip()] if rows[-1]['content'].strip() else []
        for index, projection in enumerate(projections, 1):
            clean, hits = engine.sanitise(projection)
            counts.update(hits)
            last.append(f'--- Příloha {index}: očištěná textová reprezentace ---\n{clean}')
        for name in names:
            counts.update(s.kind for s in engine.spans(name)[1])
        rows[-1]['content'] = '\n\n'.join(last)
        if not rows[-1]['content'].strip():
            fail('DLP_OUTPUT_LIMIT')
        checked = [m['content'] for m in rows] + [str(m['name']) for m in rows if m.get('name')]
        if sum(len(s) for s in checked) > cfg.max_chars:
            fail('DLP_OUTPUT_LIMIT')
        if any(engine.spans(s)[1] for s in checked) or self._analyse(checked, uid)[1]:
            fail('DLP_RECHECK')
        preview = '\n\n'.join(
            f"--- Zpráva {i} · {row['role']} ---\n" +
            (f"Název: {row['name']}\n" if row.get('name') else '') + row['content']
            for i, row in enumerate(rows, 1))
        return {'text': rows[-1]['content'], 'messages': rows, 'preview': preview,
                'counts': dict(sorted(counts.items())), 'file_count': len(files)}

    async def _check(self, body: dict, metadata: dict, uid: str, final: bool) -> dict:
        if not isinstance(body, dict) or set(body) - MODEL_FIELDS - UI_FIELDS:
            fail('DLP_REQUEST_SHAPE')
        messages = validated_messages(body)
        ids = attachment_ids(body, metadata)
        if len(ids) > self.valves.max_files or (final and ids):
            fail('DLP_LATE_OR_EXCESS_FILES')
        projections = []
        names = []
        total = 0
        for fid in ids:
            name, data = await self._read_uploaded_file(fid, uid)
            total += len(data)
            if total > self.valves.max_total_bytes:
                fail('DLP_FILE_LIMIT')
            projection = await asyncio.to_thread(extract_document, data, name, self.valves)
            projections.append(projection)
            names.append(name)
        values = [m['content'] for m in messages] + projections + names
        extras = {k: v for k, v in body.items() if k in MODEL_FIELDS and k != 'messages'}
        values += content_texts(extras)
        values += content_texts(body.get('params', {})) + content_texts(body.get('variables', {}))
        values += [str(m['name']) for m in messages if m.get('name')]
        _, hits = await asyncio.to_thread(self._analyse, values, uid)
        if hits:
            fail('DLP_SENSITIVE_DATA')
        for i, text in enumerate(projections, 1):
            messages.append({'role':'user', 'content':f'[Příloha {i}: zkontrolovaný text]\n{text}'})
        out = copy.deepcopy(body)
        out['messages'] = messages
        out.pop('files', None)
        if isinstance(out.get('metadata'), dict):
            out['metadata'].pop('files', None)
        metadata.pop('files', None)
        # Prevent adding uninspected optional sources later in the standard chat path.
        out['background_tasks'] = {}
        out['features'] = {**(out.get('features') or {}), 'memory':False,
                           'builtin_tools':False, 'web_search':False,
                           'image_generation':False, 'code_interpreter':False}
        for k in ('tools','tool_ids','tool_servers','tool_choice','skill_ids','terminal_id'):
            out.pop(k, None)
            metadata.pop(k, None)
            if isinstance(out.get('metadata'), dict):
                out['metadata'].pop(k, None)
        for container in (metadata, out.get('metadata')):
            if isinstance(container, dict):
                container['features'] = dict(out['features'])
                container['background_tasks'] = {}
        out['store'] = False  # Provider flag, NOT a claim about WebUI history retention.
        return {k:v for k,v in out.items() if k in MODEL_FIELDS} if final else out

    async def _warning(self, error, emitter):
        code = getattr(error, 'code', 'DLP_CHECK_FAILED')
        if not isinstance(code, str) or not re.fullmatch(r'DLP_[A-Z_]{1,60}', code):
            code = 'DLP_CHECK_FAILED'
        text = WARNING if code == 'DLP_SENSITIVE_DATA' else UNINSPECTABLE
        overrides = {
            'DLP_VERSION': 'Doplněk v7.1 je cílený na backend Open WebUI 0.11.3; jiná verze není povolena.',
            'DLP_TOOL_UNAVAILABLE': 'Workspace Tool není dostupný. Správce musí nastavit skutečné anonymizer_tool_id a udělit uživateli právo nástroj používat.',
            'DLP_TOOL_PROTOCOL': 'Tool a filtr nemají shodný protokol 7.1. Aktualizujte oba, zachovejte jejich skutečná ID a HMAC klíč.',
            'DLP_BROWSER_CONNECTION_REQUIRED': 'WebUI neposkytlo interaktivní spojení s prohlížečem. Požadavek nebyl předán LLM.',
            'DLP_CANCELLED': 'Dialog byl zrušen. Původní obsah nebyl předán modelu. Spouštěcí zpráva může zůstat v historii.',
            'DLP_CONTEXT_CHANGED': 'Během dialogu se změnil chat. Zadání nebylo odesláno.',
            'DLP_BROWSER_TIMEOUT': 'Prohlížeč neodpovídá na interaktivní execute události. Zadání nebylo odesláno.',
            'DLP_DIALOG_TIMEOUT': 'Vypršela doba dialogu. Zadání nebylo odesláno.',
            'DLP_TOOL_INPUT': 'Nástroj nedostal vstup z odpovídajícího filtru 7.1. Zkontrolujte obě aktualizace a vzájemná ID.',
            'DLP_TOOL_OUTPUT': 'Výsledek nástroje neodpovídá schválené struktuře požadavku. Původní obsah nebyl předán modelu.',
            'DLP_FILE_ACCESS': 'Příloha není dostupná pod vaším účtem. Původní obsah nebyl předán modelu.',
            'DLP_POLICY_CHANGED': 'Správce změnil politiku během dialogu. Zadání nebylo odesláno.',
            'DLP_GLOBAL_FILTER_INACTIVE': 'Tool vyžaduje svůj aktivní globální filtr v7.1.',
            'DLP_FILTER_UNAVAILABLE': 'Tool nenalezl svůj globální filtr. Zkontrolujte guard_filter_id ve Valves Toolu.',
            'DLP_FILTER_VERSION': 'Tool vyžaduje jádro v7.1 se shodným protokolem. Aktualizujte oba soubory.',
            'DLP_HMAC_KEY_REQUIRED': 'Správce musí ve Valves filtru nastavit náhodný HMAC klíč alespoň 32 znaků.',
        }
        text = overrides.get(code, text)
        if emitter:
            try:
                await emitter({'type':'notification', 'data':{'type':'warning', 'content':text}})
            except Exception:
                pass
        raise RuntimeError(code + ': ' + text) from None

    async def inlet(self, body: dict, __user__=None, __request__=None,
                    __metadata__=None, __event_emitter__=None, __event_call__=None) -> dict:
        try:
            verify_backend()
            uid = verified_uid(__user__)
            if __request__ is None or not isinstance(body, dict):
                fail('DLP_REQUEST_CONTEXT')
            metadata = __metadata__ if isinstance(__metadata__, dict) else (body.get('metadata') or {})
            if not isinstance(metadata, dict):
                fail('DLP_REQUEST_SHAPE')
            # IMPORTANT: branch on explicit selection BEFORE blocking PII analysis.
            selected = selected_workspace_tools(body, metadata)
            tool_id = self.valves.anonymizer_tool_id
            use_dialog = tool_id in selected
            cfg_signature = self.valves.model_dump_json()
            local = type(self)()
            local.valves = self.valves.model_copy(deep=True)
            # A failed second invocation must not inherit a successful first marker.
            if hasattr(__request__.state, REQUEST_MARKER):
                delattr(__request__.state, REQUEST_MARKER)
            if not use_dialog:
                out = await asyncio.wait_for(local._check(body, metadata, uid, False), local.valves.operation_timeout)
            else:
                pending = local.prepare_dialog_input(body, metadata, uid)
                result = await invoke_workspace_anonymizer(__request__, tool_id, uid,
                    __user__, metadata, __event_emitter__, __event_call__, pending)
                if self.valves.model_dump_json() != cfg_signature:
                    fail('DLP_POLICY_CHANGED')
                raw_result = result.get('sanitized_messages')
                if not isinstance(raw_result, list) or len(raw_result) != len(pending['messages']):
                    fail('DLP_TOOL_OUTPUT')
                clean_messages = validated_messages({'messages': raw_result})
                for original, clean, supplied in zip(pending['messages'], clean_messages, raw_result):
                    if set(supplied) - {'role','id','name','tool_call_id','content'}:
                        fail('DLP_TOOL_OUTPUT')
                    for k in ('role','id','tool_call_id'):
                        if (k in original) != (k in clean) or original.get(k) != clean.get(k):
                            fail('DLP_TOOL_OUTPUT')
                if not clean_messages[-1]['content'].strip():
                    fail('DLP_TOOL_OUTPUT')
                out = copy.deepcopy(body)
                out['messages'] = clean_messages
                # Remove EVERY original file carrier; only approved projections remain.
                out.pop('files', None)
                for container in (metadata, out.get('metadata')):
                    if isinstance(container, dict):
                        container.pop('files', None)
                pending.clear()
                # NEVER skip the check because the Tool was enabled or said approved.
                out = await asyncio.wait_for(local._check(out, metadata, uid, False), local.valves.operation_timeout)
                if __event_emitter__:
                    try:
                        await __event_emitter__({'type':'notification','data':{'type':'success',
                            'content':'Očištěný náhled byl schválen. Modelové zpracování může pokračovat po závěrečné kontrole. Uložený původní prompt, historie ani běžně nahrané přílohy se nemění a nemažou.'}})
                    except Exception:
                        pass
            setattr(__request__.state, REQUEST_MARKER, uid)
            return out
        except Exception as error:
            await self._warning(error, __event_emitter__)
        finally:
            if 'pending' in locals() and isinstance(pending, dict):
                pending.clear()

    async def request(self, body: dict, __user__=None, __request__=None,
                      __metadata__=None, __event_emitter__=None) -> dict:
        try:
            verify_backend()
            uid = verified_uid(__user__)
            if __request__ is None or getattr(__request__.state, REQUEST_MARKER, None) != uid:
                fail('DLP_PRECHECK_MISSING')
            metadata = __metadata__ if isinstance(__metadata__, dict) else {}
            return await asyncio.wait_for(self._check(body, metadata, uid, True), self.valves.operation_timeout)
        except Exception as error:
            await self._warning(error, __event_emitter__)
