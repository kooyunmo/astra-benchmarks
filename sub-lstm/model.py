import torch
import torch.nn as nn

'''
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))))
'''

from torchnlp.nn import LockedDropout
from torchnlp.nn import WeightDrop

from subLSTM.nn import SubLSTM


class RNNModel(nn.Module):
    """Container module with an encoder, a recurrent module, and a decoder."""

    def __init__(self,
                 rnn_type,
                 ntoken,
                 ninp,
                 nhid,
                 nlayers,
                 dropout=0.5,
                 dropouth=0.5,
                 dropouti=0.5,
                 dropoute=0.1,
                 wdrop=0,
                 tie_weights=False):
        super(RNNModel, self).__init__()
        self.emb_drop = LockedDropout(dropouti)
        self.idrop = nn.Dropout(dropouti)
        self.hdrop = LockedDropout(dropouth)
        self.drop = LockedDropout(dropout)
        self.encoder = nn.Embedding(ntoken, ninp)
        if rnn_type == 'LSTM':
            '''
            self.rnns = [
                torch.nn.LSTM(
                    ninp if l == 0 else nhid,
                    nhid if l != nlayers - 1 else (ninp if tie_weights else nhid),
                    1,
                    dropout=0) for l in range(nlayers)
            ]
            '''

            self.rnns = [
                SubLSTM(ninp if l == 0 else nhid,
                        nhid if l != nlayers-1 else (ninp if tie_weights else nhid),
                        num_layers=2,
                        bias=True,
                        batch_first=True) for l in range(nlayers)
            ]
            if wdrop:
                self.rnns = [WeightDrop(rnn, ['weight_hh_l0'], dropout=wdrop) for rnn in self.rnns]

        self.rnns = torch.nn.ModuleList(self.rnns)
        self.rnn = SubLSTM(ninp, nhid, num_layers=2)
        self.decoder = nn.Linear(nhid, ntoken)

        # Optionally tie weights as in:
        # "Using the Output Embedding to Improve Language Models" (Press & Wolf 2016)
        # https://arxiv.org/abs/1608.05859
        # and
        # "Tying Word Vectors and Word Classifiers: A Loss Framework for Language Modeling" (Inan et al. 2016)
        # https://arxiv.org/abs/1611.01462
        if tie_weights:
            #if nhid != ninp:
            #    raise ValueError('When using the tied flag, nhid must be equal to emsize')
            self.decoder.weight = self.encoder.weight

        self.init_weights()

        self.rnn_type = rnn_type
        self.ninp = ninp
        self.nhid = nhid
        self.nlayers = nlayers
        self.dropout = dropout
        self.dropouti = dropouti
        self.dropouth = dropouth
        self.dropoute = dropoute
        self.tie_weights = tie_weights

    def reset(self):
        if self.rnn_type == 'QRNN':
            [r.reset() for r in self.rnns]

    def init_weights(self):
        initrange = 0.1
        self.encoder.weight.data.uniform_(-initrange, initrange)
        self.decoder.bias.data.fill_(0)
        self.decoder.weight.data.uniform_(-initrange, initrange)

    def forward(self, input, hidden, return_h=False):
        emb = self.encoder(input)
        emb = self.emb_drop(emb)

        raw_output = emb
        raw_outputs = []
        outputs = []

        for l, rnn in enumerate(self.rnns):
            raw_output, hidden = rnn(raw_output)
            raw_outputs.append(raw_output)
            if l != self.nlayers - 1:
                raw_output = self.hdrop(raw_output)
                outputs.append(raw_output)
        '''
        for i in range(self.nlayers):
            print("hidden:\n{}\n".format(hidden))
            raw_output, hidden = self.rnn(raw_output, hidden)
            raw_outputs.append(raw_output)
            if i != self.nlayers - 1:
                raw_output = self.hdrop(raw_output)
                outputs.append(raw_output)
        '''
        output = self.drop(raw_output)
        outputs.append(output)

        result = output.view(output.size(0) * output.size(1), output.size(2))
        if return_h:
            return result, hidden, raw_outputs, outputs
        return result, hidden

    def init_hidden(self, bsz):
        weight = next(self.parameters()).data
        if self.rnn_type == 'LSTM':
            return [[(weight.new_zeros(1, bsz, self.nhid if l != self.nlayers - 1 else
                                      (self.ninp if self.tie_weights else self.nhid), device='cuda'),
                     weight.new_zeros(1, bsz, self.nhid if l != self.nlayers - 1 else
                                      (self.ninp if self.tie_weights else self.nhid), device='cuda'))]
                    for l in range(self.nlayers)]
