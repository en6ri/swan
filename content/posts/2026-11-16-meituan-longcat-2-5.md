---
title: Meituan publikuje LongCat-2.5, model 1,6 bln parametrów na licencji MIT, trenowany na chińskim sprzęcie
date: 2026-11-16 15:59
category: ai
lead: Chińska firma Meituan udostępniła wagi modelu agentowego LongCat-2.5 z licencją MIT. Według firmy model powstał bez układów Nvidii.
relevance: 62
why: Pasuje do tematu „nowe modele”. Otwarty model tej skali, wdrażany na akceleratorach Huawei Ascend, jest ważnym sygnałem dla rynku sprzętu.
confidence: confirmed
summary:
  - Model typu mixture-of-experts ma 1,6 bln parametrów, z czego około 48 mld aktywnych na token, i obsługuje do 1 mln tokenów wejścia.
  - Wyniki z testów, m.in. BrowseComp 91,9 i DeepSWE 64,6, pochodzą z oceny samego Meituan.
  - Przykładowe wdrożenie wymaga 194 akceleratorów Huawei Ascend; wersja 4-bitowa daje według Meituan około 43% wyższą przepustowość niż 8-bitowa.
sources:
  - The Decoder | https://the-decoder.com/meituan-releases-a-1-6-trillion-parameter-agent-model-that-never-touched-an-nvidia-gpu/ | relacja
  - The Neuron (przegląd dnia) | https://www.theneuron.ai/digest/everything-that-happened-in-ai-today-monday-november-16-2026/ | analiza
---
The Decoder pisze, że wagi pojawiły się około tydzień po oficjalnej prezentacji. Model przyjmuje tekst, obrazy i wideo, zwraca tekst, a tryb rozumowania można włączać i wyłączać. Licencja MIT pozwala na użytek komercyjny, modyfikacje i dalszą dystrybucję.

W testach podanych przez Meituan model wypada blisko czołówki, ale nie na jej szczycie. Na Terminal Bench v2.1 uzyskał 88,4 pkt wobec 89,1 dla Claude Opus 5 i 88,8 dla GPT-5.6 Sol, a na Terminal Bench v4.0 38,5 wobec 53,9 dla Opus 5. Wszystkie liczby pochodzą z własnej oceny firmy, a BrowseComp uruchomiono w jej środowisku.

Według The Decoder model trenowano wyłącznie na chińskim sprzęcie, a instrukcja wdrożenia nie zawiera wariantu dla GPU Nvidii. Promocyjna cena API to około 0,27 euro za milion tokenów wejścia i 1,07 euro za milion tokenów wyjścia.
