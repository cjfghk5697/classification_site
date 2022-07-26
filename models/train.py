# -*- coding: utf-8 -*-
"""Add valid, transforms.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/github/cjfghk5697/anomaly-detection-competition/blob/main/src/Train.ipynb
"""

from google.colab import drive
drive.mount('/content/drive')

!git clone https://github.com/DeepVoltaire/AutoAugment.git
!cp /content/drive/MyDrive/input/AutoAugment/autoaugment.py /content/drive/MyDrive/input
!cp /content/drive/MyDrive/input/AutoAugment/ops.py /content/drive/MyDrive/input

import warnings
warnings.filterwarnings('ignore')

from glob import glob
import pandas as pd
import numpy as np 
from tqdm import tqdm
import cv2

import os
#import timm
import random
from typing import Tuple, Sequence, Callable

import torch
from torch.utils.data import Dataset, DataLoader
import torch.nn as nn
import torchvision.transforms as transforms
from sklearn.metrics import f1_score, accuracy_score
import time
from PIL import Image
import cv2
from torch.autograd import Variable

from torchvision.models import mobilenet_v2

device = torch.device('cuda')

train_png = sorted(glob('./train/*.png'))

train_y = pd.read_csv('./train_df.csv')

train_labels = train_y["label"]

label_unique = sorted(np.unique(train_labels))
label_unique = {key:value for key,value in zip(label_unique, range(len(label_unique)))}

train_labels = [label_unique[k] for k in train_labels]

def img_load(path):
    img = cv2.imread(path)[:,:,::-1]
    img = cv2.resize(img, (512, 512))
    return img

train_imgs = [img_load(m) for m in tqdm(train_png)]

transforms_train = transforms.Compose([
    transforms.RandomHorizontalFlip(p=0.5),
    transforms.RandomVerticalFlip(p=0.5),
    transforms.ToTensor(),
    transforms.Normalize(
        [0.485, 0.456, 0.406],
        [0.229, 0.224, 0.225]
    )
])

class Custom_dataset(Dataset):
    def __init__(self, 
                 img_paths, 
                 labels, 
                 mode='train',
                 transforms= Sequence[Callable]
            ) -> None:
        self.img_paths = img_paths
        self.labels = labels
        self.mode=mode
        self.transforms = transforms

    def __len__(self):
        return len(self.img_paths)
    def __getitem__(self, idx):
        img = self.img_paths[idx]
        if self.mode=='train':
            augmentation = random.randint(0,2)
            if augmentation==1:
                img = img[::-1].copy()
            elif augmentation==2:
                img = img[:,::-1].copy()
        if self.mode=='test':
            pass
        img = Image.fromarray(img) # NumPy array to PIL image
        if self.transforms is not None:
            img = self.transforms(img)        
        label = self.labels[idx]
        return img, label
    
class Network(nn.Module):
    def __init__(self):
        super(Network, self).__init__()
        self.model = mobilenet_v2(pretrained=True)

    def forward(self, x):
        x = self.model(x)
        x = self.dropout(x)
        x = self.SiLU(x) 
        x = self.classifier(x)

        return x

batch_size = 32
epochs = 50

# Train
trainset  = Custom_dataset(np.array(train_imgs), np.array(train_labels), mode='train', transforms=transforms_train)
lengths = [int(len(trainset)*0.8), int(len(trainset)*0.2)]

lengths=[lengths[0],lengths[1]+1]

train_dataset, valid_dataset = torch.utils.data.random_split(trainset, lengths)

train_loader = DataLoader(train_dataset, shuffle=True, batch_size=batch_size)
valid_loader = DataLoader(valid_dataset, shuffle=True, batch_size=batch_size)

def mixup_data(x, y, alpha=1.0, use_cuda=True):
    '''Returns mixed inputs, pairs of targets, and lambda'''
    if alpha > 0:
        lam = np.random.beta(alpha, alpha)
    else:
        lam = 1

    batch_size = x.size()[0]
    if use_cuda:
        index = torch.randperm(batch_size).cuda()
    else:
        index = torch.randperm(batch_size)

    mixed_x = lam * x + (1 - lam) * x[index, :]
    y_a, y_b = y, y[index]
    return mixed_x, y_a, y_b, lam


def mixup_criterion(criterion, pred, y_a, y_b, lam):
    return lam * criterion(pred, y_a) + (1 - lam) * criterion(pred, y_b)

"""### 모델 학습"""

def score_function(real, pred):
    score = f1_score(real, pred, average="macro")
    return score

model = Network().to(device)
optimizer = torch.optim.AdamW(model.parameters(), lr=2e-4, weight_decay = 2e-2)
criterion = nn.CrossEntropyLoss()
use_amp = True
scaler = torch.cuda.amp.GradScaler(enabled=use_amp) 
lr_scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(optimizer, T_0=10, T_mult=1, eta_min=0.001, last_epoch=-1)


valid_loss_list=[]
train_loss_list=[]

for epoch in range(epochs):
    start=time.time()
    train_loss = 0
    train_pred=[]
    train_y=[]

    valid_loss = 0
    valid_pred=[]
    valid_y=[]

    model.train()
    for batch in (train_loader):
        optimizer.zero_grad()
        x = torch.tensor(batch[0], dtype=torch.float32, device=device)
        y = torch.tensor(batch[1], dtype=torch.long, device=device)

        x, targets_a, targets_b, lam = mixup_data(x, y)
        x, targets_a, targets_b = map(Variable, (x, targets_a, targets_b))

        with torch.cuda.amp.autocast():
            pred = model(x)
        loss = mixup_criterion(criterion, pred, targets_a, targets_b, lam)

        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        
        train_loss += loss.item()/len(train_loader)
        train_pred += pred.argmax(1).detach().cpu().numpy().tolist()
        train_y += y.detach().cpu().numpy().tolist()
    model.eval()
    with torch.no_grad():
      for i in (valid_loader):
          images = torch.tensor(batch[0], dtype=torch.float32, device=device)
          targets = torch.tensor(batch[1], dtype=torch.long, device=device)



          outputs = model(images)
          loss = criterion(outputs, targets)

          valid_loss += loss.item()/len(valid_loader)
          valid_pred += outputs.argmax(1).detach().cpu().numpy().tolist()
          valid_y += targets.detach().cpu().numpy().tolist()
    
    train_f1 = score_function(train_y, train_pred)
    valid_f1 = score_function(valid_y, valid_pred)

    TIME = time.time() - start
    print(f'epoch : {epoch+1}/{epochs}    time : {TIME:.0f}s/{TIME*(epochs-epoch-1):.0f}s')
    print(f'TRAIN    loss : {train_loss:.5f}    f1 : {train_f1:.5f}')
    print(f'valid    loss : {valid_loss:.5f}    f1 : {valid_f1:.5f}')
    lr_scheduler.step()

    torch.save(model.state_dict(), f'{train_loss}_{train_f1}.pth')