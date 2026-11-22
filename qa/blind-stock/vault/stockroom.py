"""New, nonmonetary NQC fixture. One batch moves stock between two shelves."""
def run(variant, opening, slips):
    left, right = opening
    amounts = []
    for quantity, pack, cancelled in slips:
        units = quantity * pack
        if variant == "cartons_as_units" and pack > 1:
            units = quantity
        if cancelled and variant != "void_slip_posted":
            units = 0
        amounts.append(units)

    if variant == "clean_sequential":
        closing = list(opening)
        for units in amounts:
            closing[0] -= units
            closing[1] += units
        outgoing, incoming = closing
    elif variant == "clean_column_totals":
        outgoing = sum([left, *(-n for n in amounts)])
        incoming = sum([right, *amounts])
    elif variant == "clean_reverse_visit":
        outgoing, incoming = left, right
        for units in reversed(amounts):
            incoming += units
            outgoing -= units
    else:
        outgoing = left - sum(amounts)
        incoming = right + sum(amounts)

    entries = list(amounts)
    count = sum(n > 0 for n in amounts)
    subtotal = outgoing + incoming
    if variant == "largest_arrival_only":
        incoming = right + max(amounts)
    elif variant == "narrow_closing_column":
        outgoing %= 256
    elif variant == "count_distinct_sizes":
        count = len({n for n in amounts if n})
    elif variant == "three_digit_subtotal":
        subtotal %= 1000
    elif variant == "reversed_line_order":
        entries.reverse()
    elif variant == "short_second_book_entry" and entries[1] > 1:
        entries[1] -= 1
    return {"book": entries, "report": {"left": outgoing, "right": incoming, "rows": count, "total": subtotal}}
