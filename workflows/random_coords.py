import logging
import numpy as np
import random
import cv2

def gen_random_coordinates(img_path: str, mask_path: str, count: int = 0):
    """
    RANDOM COORDS GENERATOR
    _______________________________
    @img_path: path to image
    @mask_path: path to mask
    @count: number of random particles to generate
    """
    def generate_random_points(boundary: list, quantity: int, mask: list):
        # print('bound', boundary)
        # generate faux particles within the pface
        coords = []
        num = 0
        while num < quantity:
            x = random.randint(1, boundary[0] - 1)
            y = random.randint(1, boundary[1] - 1)
            if mask[x, y] != 0:
                coords.append((x, y))
                num += 1
        # print(f"The total number of particles inside the p-face are {count}.")
        return coords

    if len(img_path) == 0:
        return []
    # import img
    img_original = cv2.imread(img_path)
    crop = img_original.shape
    # if no mask provided, use the entire image
    if len(mask_path) > 0:
        img_pface = cv2.imread(mask_path)
    else:
        img_pface = np.zeros(crop, dtype=np.uint8)
        img_pface.fill(245)
    # crop to size of normal image
    img_pface = img_pface[:crop[0], :crop[1], :3]
    # convert to grayscale
    img_pface2 = cv2.cvtColor(img_pface, cv2.COLOR_BGR2GRAY)
    # print(img_pface2.shape, img_pface2)
    # # cv2.imwrite('pface_contours1.png', img_pface)
    # # convert to binary
    ret, binary = cv2.threshold(img_pface2, 100, 255, cv2.THRESH_OTSU)
    # print('converted to binary')
    # print(binary.shape, binary)
    # cv2.imwrite('pface_contours2.png', binary)
    # get border of pface mask
    # contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    # with_contours = cv2.drawContours(
    #     img_original, contours, -1, (255, 0, 255), 3)
    # cv2.imwrite('pface_contours4.png', with_contours)
    # print('converted to mask')

    # hsv = cv2.cvtColor(img_pface, cv2.COLOR_BGR2HSV)
    # lower_bound = np.array([0, 0, 0])
    # upper_bound = np.array([179, 100, 130])
    # pface_mask: list = cv2.inRange(hsv, lower_bound, upper_bound)
    # print('converted to mask 2')
    pface_mask = ~binary

    # # grab contours of pface
    # lower_bound = np.array([239, 174, 0])
    # upper_bound = np.array([254, 254, 254])
    # pface_mask: list = cv2.inRange(img_pface, lower_bound, upper_bound)
    # print(pface_mask.shape, pface_mask)
    
    logging.info("Generated random particles")
    # print('mask', img_pface, lower_bound, upper_bound)
    return generate_random_points(pface_mask.shape, count, pface_mask)
