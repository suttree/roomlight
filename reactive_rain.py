def draw_frame(draw, t, audio, width, height):
    strength = audio['pulse'] * 0.18 if audio['quiet'] else audio['level']
    for i in range(18):
        band = 0 if audio['quiet'] else audio['bands'][i % 24]
        energy = min(1, strength * 0.7 + band * 0.3)
        x = 10 + 320 * i / 18
        y = (t * 37 + i * 31) % 220
        length = 8 + 115 * energy
        colour = (int(50 + 170 * energy), int(80 + 175 * energy), int(120 + 110 * energy))
        draw.line((x, y, x, y + length), fill=colour, width=2 + int(6 * energy))
