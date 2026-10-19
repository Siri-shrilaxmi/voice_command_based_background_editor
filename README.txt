# Voice-Controlled Photo Editor - Dummy Frontend

## Folder structure

Place these files/folders together:

project/
├── index.html
├── backgrounds.csv
└── backgrounds/
    ├── img2.jpg
    └── img3.jpg

The image extensions can also be .jpeg, .png, or .webp.

## Mapping

Option 1 = Background Removal / White Background
Option 2 = Background Blur

For custom backgrounds:

CSV img_id 1 -> img2 -> Frontend Option 3
CSV img_id 2 -> img3 -> Frontend Option 4
CSV img_id 3 -> img4 -> Frontend Option 5

In general:

frontend option = CSV img_id + 2
filename = "img" + (CSV img_id + 1)

## Current functionality

- Select an input photo.
- Displays the selected photo.
- Reads backgrounds.csv.
- Displays custom background images from the backgrounds folder.
- Shows the correct frontend option numbers and names.
- Provides buttons to select an option (currently only logs the selection).
- Provides browser speech recognition and displays the recognized voice command as text.

## Important

This is intentionally only the dummy frontend.

It does NOT call the image-processing backend yet.

The backend can later receive:
- the uploaded image
- the selected option OR the recognized voice command

and perform the rembg/OpenCV processing.
