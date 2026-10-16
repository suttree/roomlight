# Handwritten recovery of the daily sound-ripples brief, not unedited model output.
def draw_frame(draw, t, audio, width, height):
    strength = audio['pulse'] if audio['quiet'] else audio['level']
    for i in range(8):
        radius = 10 + (i * 13 + t * 39) % 110 + 30 * strength
        colour = (int(40+49*strength), int(120+135*strength), int(90+103*strength))
        draw.ellipse((180-radius, 180-radius, 180+radius, 180+radius), outline=colour, width=3)
