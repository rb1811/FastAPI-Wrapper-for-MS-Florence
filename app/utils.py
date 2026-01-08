import matplotlib.pyplot as plt
import matplotlib.patches as patches
from PIL import Image, ImageDraw, ImageFont
import random
import numpy as np
from matplotlib.colors import to_rgba
import io
from app.logging_config import get_logger

# Use the structured logger
logger = get_logger(__name__)

colormap = ['blue', 'orange', 'green', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan', 'red',
            'lime', 'indigo', 'violet', 'aqua', 'magenta', 'coral', 'gold', 'tan', 'skyblue']

# app/utils.py

def plot_bbox(image, data):
    # Florence-2 uses different keys for different tasks:
    # <OD> / <OBJECT_DETECTION> usually use 'labels'
    # <OPEN_VOCABULARY_DETECTION> often uses 'bboxes_labels'
    bboxes = data.get('bboxes', [])
    labels = data.get('labels') or data.get('bboxes_labels') or []

    logger.info("Generating Bounding Box plot", 
                num_boxes=len(bboxes),
                labels=labels)
    
    fig, ax = plt.subplots()
    ax.imshow(image)
    
    try:
        # If labels is empty, we create generic labels so zip doesn't fail
        if not labels and bboxes:
            labels = [f"obj_{i}" for i in range(len(bboxes))]

        for bbox, label in zip(bboxes, labels):
            x1, y1, x2, y2 = bbox
            rect = patches.Rectangle((x1, y1), x2-x1, y2-y1, linewidth=2, edgecolor='r', facecolor='none')
            ax.add_patch(rect)
            plt.text(x1, y1-5, label, color='white', fontsize=10, bbox=dict(facecolor='red', alpha=0.8))
            
    except Exception as e:
        logger.error("Error in plot_bbox drawing loop", error=str(e), data_received=str(data))

    ax.axis('off')
    plt.tight_layout()
    return fig


def draw_polygons(image, prediction, fill_mask=False):
    draw = ImageDraw.Draw(image)
    width, height = image.size
    
    polygons = prediction.get('polygons', [])
    labels = prediction.get('labels', [])
    
    logger.info("Drawing polygons for segmentation", 
                img_size=f"{width}x{height}", 
                num_polygons=len(polygons))

    if polygons and isinstance(polygons[0], list) and isinstance(polygons[0][0], list):
        polygons = polygons[0]

    color = (255, 0, 0, 128)  # Red with 50% opacity
    outline_color = (255, 0, 0)  # Solid red for outline

    try:
        if not polygons:
            logger.warning("No polygons found in prediction data")
            return image

        scaled_polygon = [(max(0, min(int(x), width - 1)), max(0, min(int(y), height - 1))) 
                          for x, y in zip(polygons[0][::2], polygons[0][1::2])]
        
        if len(scaled_polygon) > 2:
            if fill_mask:
                draw.polygon(scaled_polygon, fill=color, outline=outline_color)
            else:
                draw.line(scaled_polygon + [scaled_polygon[0]], fill=outline_color, width=3)

        draw.text((10, 10), "Segmentation applied", fill=(255, 0, 0))
        logger.debug("Successfully drew polygon", point_count=len(scaled_polygon))
        
    except Exception as e:
        logger.exception("Error drawing polygon", error=str(e))

    return image

def draw_ocr_bboxes(image, prediction):
    draw = ImageDraw.Draw(image)
    quad_boxes = prediction.get('quad_boxes', [])
    
    logger.info("Drawing OCR bounding boxes", count=len(quad_boxes))

    try:
        # Attempt to use a cleaner font, fallback to default
        font = ImageFont.truetype("arial.ttf", 15)
    except IOError:
        font = ImageFont.load_default()

    for i, (box, label) in enumerate(zip(quad_boxes, prediction.get('labels', []))):
        color = random.choice(colormap)
        box_coords = np.array(box).reshape(-1, 2)
        draw.polygon(box_coords.flatten().tolist(), outline=color, width=2)
        draw.text((box_coords[0][0], box_coords[0][1]-20), f"{label[:10]}", fill=color, font=font)
    
    return image

def fig_to_pil(fig):
    logger.debug("Converting Matplotlib figure to PIL image")
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    return Image.open(buf)