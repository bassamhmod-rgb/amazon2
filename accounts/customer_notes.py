def apply_customer_private_note(note, private_note, previous=""):
    note = (note or "").rstrip()
    previous = (previous or "").strip()
    private_note = (private_note or "").strip()
    if previous and previous != private_note:
        if note == previous:
            note = ""
        elif note.endswith("\n" + previous):
            note = note[:-len(previous)].rstrip()
    if not private_note or "\n" + private_note + "\n" in "\n" + note + "\n":
        return note
    return note + "\n" + private_note if note else private_note
