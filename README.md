# AWS Logs GUI

AWS CloudWatch loglarını görüntülemek ve filtrelemek için kullanıcı dostu bir GUI uygulaması.

## Özellikler

- Çoklu ortam desteği (QA, Sandbox, Production)
- Gerçek zamanlı log görüntüleme
- Gelişmiş filtreleme özellikleri
- Zamana göre sıralama
- Renkli log görüntüleme
- Arama ve filtreleme için highlight özelliği
- Log dışa aktarma
- Çoklu AWS profil desteği

## Gereksinimler

- Python 3.8+
- AWS CLI yapılandırılmış olmalı
- AWS profilleri tanımlanmış olmalı

## Kurulum

1. Repoyu klonlayın:
```bash
git clone https://bitbucket.org/bumin/awslogs-w-gui.git
cd awslogs-w-gui
```


2. Gerekli paketleri yükleyin:
```bash
aws configure list-profiles
```


## Kullanım

1. Uygulamayı başlatın:
```bash
python main.py
```

2. Ortam seçin (QA/SB/PROD)
3. Aranacak metni girin
4. Zaman aralığını belirleyin:
   - Saat cinsinden (örn: "1" = son 1 saat)
   - Veya spesifik tarih (örn: "2025-01-20 22:44:44")
5. "Ara" butonuna tıklayın

### Filtreleme

- Üst kısımdaki "Search" alanı AWS CloudWatch filtresi için kullanılır
- Alt kısımdaki "Filtrele" alanı bulunan loglar içinde filtreleme yapar
- Her iki filtrede de highlight özelliği mevcuttur

### Ayarlar

Ayarlar menüsünden:
- Her ortam için AWS profilleri tanımlanabilir
- Log pathleri düzenlenebilir
- Highlight özellikleri açılıp kapatılabilir
- Otomatik sıralama özelliği ayarlanabilir

## Konfigürasyon

`config.json` dosyası üzerinden:
- AWS profilleri
- Log pathleri
- Görünüm ayarları
yapılandırılabilir.

## Notlar

- AWS profilleri önceden yapılandırılmış olmalıdır
- Yeterli AWS izinlerine sahip olduğunuzdan emin olun
- Çok sayıda log varsa filtreleme kullanmanız önerilir

## Hata Giderme

1. AWS profil hatası:
   - AWS CLIın kurulu olduğundan emin olun
   - Profillerin doğru yapılandırıldığını kontrol edin

2. Log görüntüleme hatası:
   - AWS izinlerinizi kontrol edin
   - Log group pathlerinin doğruluğunu kontrol edin