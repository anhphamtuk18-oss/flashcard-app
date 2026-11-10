# Lexi — ứng dụng học từ vựng bằng flashcard

Ứng dụng desktop viết bằng Python và PyQt5. Cửa sổ chính được dựng trong Qt Designer ở `mainWindow.ui`, còn `main.py` nạp giao diện và xử lý các thao tác.

## Chức năng

- Tạo nhiều bộ thẻ và tìm bộ thẻ theo tên.
- Thêm, sửa, xóa thẻ gồm từ vựng, nghĩa và câu ví dụ.
- Lật thẻ, chuyển thẻ trước/sau, đánh dấu từ đã nhớ hoặc cần ôn lại.
- Phát âm mẫu tiếng Anh và ghi âm giọng đọc trong 5 giây.
- Chấm điểm ước lượng bằng cách so độ khớp giữa từ mục tiêu và kết quả nhận dạng.
- Làm câu hỏi trắc nghiệm ngẫu nhiên từ bộ thẻ đang chọn.
- Tự lưu dữ liệu vào `data/flashcards.json` cạnh ứng dụng.

## Chạy ứng dụng

Mở PowerShell tại thư mục này rồi chạy:

```powershell
python -m pip install -r requirements.txt
python main.py
```

Hoặc chạy `run.bat` trên Windows. Lần đầu chạy, ứng dụng tự tạo bộ thẻ mẫu và tệp dữ liệu.

## Phát âm và chấm điểm nói

- **Nghe mẫu** dùng giọng tiếng Anh có sẵn trên Windows thông qua `pyttsx3`.
- **Nói và chấm điểm** dùng micro cùng Vosk để nhận dạng tiếng Anh ngay trên máy. Lần đầu bấm nút, ứng dụng hỏi tải model tiếng Anh khoảng 40 MB từ [Vosk](https://alphacephei.com/vosk/models); model được lưu trong thư mục `models`.
- Điểm 0–100 phản ánh mức khớp văn bản nhận dạng với từ trên thẻ. Đây là điểm luyện tập ước lượng, không phải phân tích âm vị chuyên sâu; độ chính xác phụ thuộc micro, giọng đọc và model nhận dạng.

## Chỉnh sửa giao diện

Mở `mainWindow.ui` trong Qt Designer để chỉnh bố cục. Giữ nguyên tên `objectName` của các widget đang được `main.py` sử dụng. Ứng dụng nạp trực tiếp tệp `.ui`, nên không cần chạy `pyuic5` sau khi sửa giao diện.
