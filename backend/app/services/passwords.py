"""Password policy, enforced whenever a password is set or changed (signup, change, reset, staff creation). Sign-in never applies it,
so existing accounts keep working until their owner changes the password.

Rules: 8 to 72 bytes (bcrypt reads only the first 72), not on the common-password list, not the e-mail address, its local part, the
name or the phone number, not one repeated character, not a plain run like 12345678 or abcdefgh, and at least two kinds of character.
"""
import re

MIN_LEN = 8
MAX_BYTES = 72

COMMON = frozenset("""
password password1 password12 password123 password1234 passw0rd p@ssw0rd p@ssword pass1234 pass12345 passpass qwerty qwerty1 qwerty12 qwerty123 qwertyui qwertyuiop
qwerty1234 qwerty12345 asdfghjk asdfghjkl asdf1234 zxcvbnm zxcvbnm1 1q2w3e4r 1q2w3e4r5t 1qaz2wsx 1qazxsw2 zaq12wsx q1w2e3r4 q1w2e3r4t5 abc12345 abcd1234 abcd12345
abcdefgh abcdefg1 abc123456 12345678 123456789 1234567890 12345678910 123123123 1234qwer 12341234 11111111 111111111 00000000 000000000 12121212 11223344 99999999 88888888
87654321 987654321 0987654321 111222333 123321123 123454321 1234abcd 123abc123 a1b2c3d4 a1234567 a12345678 aa123456 aaaa1111 admin123 admin1234 admin12345 administrator
adminadmin welcome1 welcome12 welcome123 letmein1 letmein12 letmein123 iloveyou iloveyou1 iloveyou123 monkey123 dragon123 master123 sunshine sunshine1 princess princess1
football football1 baseball baseball1 superman superman1 trustno1 changeme changeme1 changeme123 change123 default123 test1234 test12345 testtest testing123 temp1234 temp12345
login123 secret123 secret1234 shadow123 michael1 jordan23 charlie1 donald123 hello123 hello1234 hello12345 freedom1 whatever whatever1 computer computer1 internet internet1
starwars starwars1 flower123 lovelove lovely123 abcabc123 qazwsxedc qazwsx123 qweasdzxc qweasd123 zxcasdqwe 1qaz1qaz asdasd123 asd12345 asdasdasd mynameis1 nopassword
flatwise flatwise1 flatwise123 flatwise1234 flat1234 flat12345 building123 building1 apartment1 owner123 owner1234 tenant123 tenant1234 manager123 manager1234 guard1234
caretaker1 demo1234 demo12345 demodemo demo123456 bangladesh bangladesh1 bangladesh123 dhaka123 dhaka1234 dhaka12345 dhaka1212 chittagong1 sylhet123 khulna123 rajshahi1
bismillah bismillah1 allah123 allah1234 muhammad1 mohammad1 mohammed1 rahman123 karim1234 rahim1234 amarsonarbangla jononi123 ami123456 tumi12345 bangla123 bangla1234
iloveyou2 password! password. password@123 password#1 pa$$w0rd pa55word pa55w0rd p4ssw0rd p4ssword welcome@123 admin@123 admin@1234 abc@1234 abc@12345 qwerty@123 test@123
india123 pakistan1 india1234 user1234 user12345 guest1234 root1234 rootroot toor1234 mysql123 oracle123 server123 system123 master1234 office123 company1 company123
""".split())

_KINDS = (re.compile(r"[a-z]"), re.compile(r"[A-Z]"), re.compile(r"[0-9]"), re.compile(r"[^A-Za-z0-9]"))


def _run(s: str) -> bool:
    """True for plain ascending or descending runs such as 12345678, 87654321, abcdefgh."""
    if len(s) < 6:
        return False
    step = ord(s[1]) - ord(s[0])
    return step in (1, -1) and all(ord(s[i + 1]) - ord(s[i]) == step for i in range(len(s) - 1))


def check(password: str, *, email: str = "", name: str = "", phone: str = "") -> str | None:
    """None if acceptable, else a short message for the person (plain language, safe to show)."""
    pw = password or ""
    if len(pw) < MIN_LEN:
        return f"Use at least {MIN_LEN} characters."
    if len(pw.encode()) > MAX_BYTES:
        return "Use at most 72 characters (or fewer if you use Bangla letters)."
    low = pw.lower()
    if low in COMMON or re.sub(r"[^a-z0-9]", "", low) in COMMON:
        return "This password is too common. Pick something harder to guess."
    if len(set(pw)) < 3 or _run(low):
        return "This password is too simple. Mix letters and numbers."
    if sum(1 for k in _KINDS if k.search(pw)) < 2 and not re.search(r"[^\x00-\x7f]", pw):
        return "Mix at least two of: lowercase, uppercase, numbers, symbols."
    e = (email or "").strip().lower()
    personal = {x for x in (e, e.split("@")[0], (name or "").strip().lower(), re.sub(r"\D", "", phone or "")) if len(x) >= 4}
    squashed = re.sub(r"\s+", "", low)
    if any(low == x or squashed == re.sub(r"\s+", "", x) for x in personal):
        return "Your password must not be your email, name or phone number."
    return None
