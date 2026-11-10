# Lexi — ứng dụng học từ vựng bằng flashcard

Ứng dụng desktop viết bằng Python và PyQt5. Cửa sổ chính được thiết kế trong mainWindow.ui; main.py nạp giao diện và xử lý chức năng. Dữ liệu được lưu cục bộ trong data/flashcards.json.

## Phiên bản 1.1 — Bản đầu tiên

Phiên bản đầu tiên cung cấp các chức năng flashcard cơ bản:

- Tạo và tìm kiếm nhiều bộ thẻ.
- Thêm, chỉnh sửa, xóa từ vựng; mỗi thẻ gồm từ, nghĩa và câu ví dụ.
- Lật thẻ để xem nghĩa, chuyển sang thẻ trước hoặc tiếp theo.
- Đánh dấu từ đã nhớ hoặc cần ôn lại.
- Kiểm tra trắc nghiệm ngẫu nhiên trong bộ thẻ đang chọn.
- Lưu bộ thẻ và trạng thái ghi nhớ trên máy để dùng lại khi mở ứng dụng.

## Phiên bản 1.2 — Lexi 1.2

Phiên bản 1.2 giữ các chức năng của 1.1 và bổ sung, chỉnh sửa:

- **Tạo chủ đề kèm từ vựng:** nhập tên, mô tả và nhiều từ ngay trong hộp thoại tạo chủ đề. Mỗi dòng theo dạng từ | nghĩa | ví dụ; ví dụ có thể bỏ trống. Cần nhập ít nhất một từ.
- **Nghe phát âm mẫu:** đọc từ đang hiện trên flashcard bằng giọng tiếng Anh có sẵn trên Windows.
- **Luyện nói và chấm điểm:** ghi âm 5 giây, nhận dạng tiếng Anh cục bộ và chấm mức khớp ước lượng từ 0–100.
- **Phát âm theo đúng thẻ hiện tại:** nghe mẫu và chấm điểm luôn dùng từ đang hiển thị, kể cả khi thứ tự học đã được trộn.
- **Hàng chờ theo lượt học:** từ được trộn khi bắt đầu lượt. Bấm Đã nhớ sẽ loại từ khỏi hàng chờ hiện tại. Bấm Cần ôn lại sẽ chuyển sang từ khác và chèn từ cần ôn ngẫu nhiên vào phần còn lại của hàng chờ.
- **Hoàn thành và học lại:** khi đã xử lý hết hàng chờ, ứng dụng báo hoàn thành. Bấm Học lại bộ thẻ sẽ đặt lại trạng thái ghi nhớ và bắt đầu lượt mới từ ĐÃ NHỚ 0/n TỪ.
- **Sửa nút điều hướng:** nút Học lại bộ thẻ chỉ hiện ở trạng thái hoàn thành; khi đang học, nút trở về chức năng chuyển thẻ.

Điểm nói là mức khớp văn bản nhận dạng với từ mục tiêu, không phải phân tích âm vị chuyên sâu. Kết quả có thể thay đổi theo micro, giọng đọc và model.

### Thiết lập phát âm

Cài thư viện trong requirements.txt. Lần đầu bấm Nói và chấm điểm, ứng dụng sẽ hỏi tải model tiếng Anh Vosk khoảng 40 MB vào thư mục models. Nhận dạng chạy cục bộ sau khi tải model. Nút Nghe mẫu dùng pyttsx3 và giọng tiếng Anh đã cài trên Windows.

## Chạy ứng dụng

Mở PowerShell tại thư mục dự án và chạy:

python -m pip install -r requirements.txt
python main.py

Hoặc chạy run.bat trên Windows. Lần đầu mở ứng dụng, chương trình tạo bộ thẻ mẫu và tệp dữ liệu nếu chưa có.

## Chỉnh sửa giao diện

Mở mainWindow.ui trong Qt Designer. Giữ nguyên objectName của các widget mà main.py sử dụng. Ứng dụng nạp trực tiếp tệp .ui nên không cần chạy pyuic5 sau khi sửa giao diện.
