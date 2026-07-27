def parse_horario(texto: str):
    import re
    texto = texto.lower().strip()
    if "meio dia" in texto or "meio-dia" in texto: return 12, 0
    if "meia noite" in texto or "meia-noite" in texto: return 0, 0
    
    match = re.search(r"(\d{1,2})(?:[^\d]+(\d{2}))?|(\d{1,2})", texto)
    if match:
        # group 1/2 for '12:30' or '12h30', group 3 for just '12'
        if match.group(3):
            hora = int(match.group(3))
            minuto = 0
        else:
            hora = int(match.group(1))
            minuto = int(match.group(2)) if match.group(2) else 0
            
        if "tarde" in texto and 1 <= hora <= 11:
            hora += 12
        elif "noite" in texto and 1 <= hora <= 11:
            hora += 12
        return hora, minuto
    return None, None

for t in ["12:30", "12h30", "15", "15 horas", "2 da tarde", "meio dia", "uma da tarde", "8 da noite"]:
    print(t, "->", parse_horario(t))
