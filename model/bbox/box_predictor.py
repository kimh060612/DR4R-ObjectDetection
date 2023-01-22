import torch
from torch import nn
import math
from ..backbone.mobilenetv2 import DepthwiseSeparableConv

class BoxPredictor(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.cls_headers = nn.ModuleList()
        self.reg_headers = nn.ModuleList()
        for level, (boxes_per_location, out_channels) in enumerate(zip(cfg.MODEL.PRIORS.BOXES_PER_LOCATION, cfg.MODEL.BACKBONE.OUT_CHANNELS)):
            cls_head = self.cls_block(level, out_channels, boxes_per_location)
            self.cls_headers.append(cls_head)

            reg_head = self.reg_block(level, out_channels, boxes_per_location)
            self.reg_headers.append(reg_head)
        self.reset_parameters()

        if self.cfg.MODEL.BOX_HEAD.LOSS == 'FocalLoss':
            for cls_head in self.cls_headers:
                for m in cls_head.modules():
                    if isinstance(m, nn.Conv2d):
                        m.apply(self.initialize_prior)

    def reset_parameters(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.xavier_uniform_(m.weight)
                nn.init.zeros_(m.bias)
    
    def initialize_prior(self, layer):
        pi = 0.01
        b = - math.log((1 - pi) / pi)
        nn.init.constant_(layer.bias, b)
        nn.init.normal_(layer.weight, std=0.01)

    def forward(self, features):
        cls_logits = []
        bbox_pred = []
        for feature, cls_header, reg_header in zip(features, self.cls_headers, self.reg_headers):
            cls_logits.append(cls_header(feature).permute(0, 2, 3, 1).contiguous())
            bbox_pred.append(reg_header(feature).permute(0, 2, 3, 1).contiguous())

        batch_size = features[0].shape[0]
        cls_logits = torch.cat([c.view(c.shape[0], -1) for c in cls_logits], dim=1).view(batch_size, -1, self.cfg.MODEL.NUM_CLASSES)
        bbox_pred = torch.cat([l.view(l.shape[0], -1) for l in bbox_pred], dim=1).view(batch_size, -1, 4)

        return cls_logits, bbox_pred

class SSDLiteBoxPredictor(BoxPredictor):
    def cls_block(self, level, out_channels, boxes_per_location):
        num_levels = len(self.cfg.MODEL.BACKBONE.OUT_CHANNELS)
        if level == num_levels - 1:
            return nn.Conv2d(out_channels, boxes_per_location * self.cfg.MODEL.NUM_CLASSES, kernel_size=1)
        return DepthwiseSeparableConv(out_channels, boxes_per_location * self.cfg.MODEL.NUM_CLASSES, kernel_size=3, stride=1, padding=1)

    def reg_block(self, level, out_channels, boxes_per_location):
        num_levels = len(self.cfg.MODEL.BACKBONE.OUT_CHANNELS)
        if level == num_levels - 1:
            return nn.Conv2d(out_channels, boxes_per_location * 4, kernel_size=1)
        return DepthwiseSeparableConv(out_channels, boxes_per_location * 4, kernel_size=3, stride=1, padding=1)
