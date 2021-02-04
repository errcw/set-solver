package ca.ericw.setsolver;

import android.Manifest;
import android.content.ContentValues;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Matrix;
import android.graphics.Paint;
import android.graphics.Rect;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.provider.Settings;
import android.util.ArrayMap;
import android.util.Log;
import android.view.MotionEvent;
import android.view.View;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.FileProvider;
import androidx.exifinterface.media.ExifInterface;

import com.android.volley.DefaultRetryPolicy;
import com.android.volley.Request;
import com.android.volley.RequestQueue;
import com.android.volley.VolleyError;
import com.android.volley.toolbox.JsonObjectRequest;
import com.android.volley.toolbox.Volley;
import com.google.android.material.snackbar.Snackbar;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

import ca.ericw.setsolver.databinding.ActivityMainBinding;

public class MainActivity extends AppCompatActivity {

  private static final String SOLVE_URL = "https://ffkbmc379f.execute-api.us-east-2.amazonaws.com/Prod/solve";

  private static final int[] SET_HIGHLIGHT_COLORS = new int[] {
      Color.rgb(139, 214, 242),
      Color.rgb(139, 242, 167),
      Color.rgb(242, 167, 139),
      Color.rgb(242, 139, 214),
      Color.rgb(242, 219, 139),
      Color.rgb(123, 247, 222)
  };
  private static final int SET_HIGHLIGHT_WIDTH = 50;

  private final ActivityResultLauncher<Uri> capturePhoto = registerForActivityResult(
      new ActivityResultContracts.TakePicture(),
      this::onTakePhotoResult);

  private final ActivityResultLauncher<String> requestPermission = registerForActivityResult(
      new ActivityResultContracts.RequestPermission(),
      this::onCameraPermissionResult);

  private ActivityMainBinding binding;

  private RequestQueue httpQueue;

  private Uri photoUri;
  private Bitmap photoBitmap;
  private Map<String, Rect> detectedCards;

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);

    binding = ActivityMainBinding.inflate(getLayoutInflater());
    setContentView(binding.getRoot());

    binding.scan.setOnClickListener(this::onScanClick);
    binding.imageView.setOnTouchListener(this::onImageTouch);

    httpQueue = Volley.newRequestQueue(this);
  }

  @Override
  protected void onStart() {
    super.onStart();
    requestPermission.launch(Manifest.permission.CAMERA);
    enableScanButton();
  }

  private void onScanClick(View v) {
    // Reset previous state.
    photoUri = null;
    photoBitmap = null;
    detectedCards = null;

    // Capture a new photo.
    ContentValues contentValues = new ContentValues();
    contentValues.put(MediaStore.MediaColumns.DISPLAY_NAME, "SET Solver Photo");
    contentValues.put(MediaStore.MediaColumns.MIME_TYPE, "image/jpeg");
    contentValues.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DCIM);
    photoUri = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, contentValues);
    capturePhoto.launch(photoUri);
  }

  private boolean onImageTouch(View v, MotionEvent e) {
    if (e.getAction() == MotionEvent.ACTION_DOWN && detectedCards != null) {
      Matrix inverse = new Matrix();
      binding.imageView.getImageMatrix().invert(inverse);
      float[] touchPts = new float[] {e.getX(), e.getY()};
      inverse.mapPoints(touchPts);

      int touchX = (int) touchPts[0];
      int touchY = (int) touchPts[1];
      Log.d("SetSolver", "X=" + touchX + ", Y=" + touchY);

      for (Map.Entry<String, Rect> card : detectedCards.entrySet()) {
        if (card.getValue().contains(touchX, touchY)) {
          binding.cardLabel.setText(card.getKey());
        }
      }
    } else if (e.getAction() == MotionEvent.ACTION_UP) {
      binding.cardLabel.setText("");
    }
    return true;
  }

  private void onCameraPermissionResult(boolean granted) {
    binding.scan.setEnabled(granted);
    if (!granted) {
      if (shouldShowRequestPermissionRationale(Manifest.permission.CAMERA)) {
        Snackbar
            .make(
                binding.getRoot(),
                R.string.camera_permission_rationale,
                Snackbar.LENGTH_INDEFINITE)
            .setAction(R.string.ok, v -> requestPermission.launch(Manifest.permission.CAMERA))
            .show();
      } else {
        Snackbar
            .make(
                binding.getRoot(),
                R.string.camera_permission_denied_explanation,
                Snackbar.LENGTH_INDEFINITE)
            .setAction(R.string.settings, v -> {
              Intent intent = new Intent();
              intent.setAction(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
              intent.setData(Uri.fromParts("package", BuildConfig.APPLICATION_ID, null));
              intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
              startActivity(intent);
            })
            .show();
      }
    }
  }

  private void onTakePhotoResult(boolean success) {
    if (success) {
      disableScanButton();
      try {
        sendHttpSolveRequest(readCapturedPhoto());
      } catch (IOException e) {
        showUnexpectedFailureSnackbar("Failure reading captured photo", e);
      }
    } else {
      showUnexpectedFailureSnackbar("Failure capturing photo", null);
    }
  }

  private byte[] readCapturedPhoto() throws IOException{
    // Read the raw JPEG bytes (which will eventually be uploaded).
    ByteArrayOutputStream bos = new ByteArrayOutputStream();
    InputStream is = getContentResolver().openInputStream(photoUri);
    int readBytes;
    byte[] buf = new byte[16384];
    while ((readBytes = is.read(buf, 0, buf.length)) != -1) {
      bos.write(buf, 0, readBytes);
    }
    byte[] jpegBytes = bos.toByteArray();

    // Convert the JPEG into a drawable bitmap.
    BitmapFactory.Options bmOptions = new BitmapFactory.Options();
    bmOptions.inMutable = true; // Allow the overlay to be drawn.
    photoBitmap = BitmapFactory.decodeByteArray(jpegBytes, 0, jpegBytes.length, bmOptions);

    // Rotate if necessary. Server-side OpenCV will rotate the image based on this same metadata
    // so any results we get will be transformed with this rotation.
    ExifInterface exif = new ExifInterface(getContentResolver().openInputStream(photoUri));
    int rotation = exif.getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL);
    switch (rotation) {
      case ExifInterface.ORIENTATION_ROTATE_90:
        photoBitmap = rotateBitmap(photoBitmap, 90);
        break;
      case ExifInterface.ORIENTATION_ROTATE_180:
        photoBitmap = rotateBitmap(photoBitmap, 180);
        break;
      case ExifInterface.ORIENTATION_ROTATE_270:
        photoBitmap = rotateBitmap(photoBitmap, 270);
        break;
      default:
        break;
    }

    binding.imageView.setImageBitmap(photoBitmap);

    return jpegBytes;
  }

  private static Bitmap rotateBitmap(Bitmap img, int degrees) {
    Matrix matrix = new Matrix();
    matrix.postRotate(degrees);
    return Bitmap.createBitmap(img, 0, 0, img.getWidth(), img.getHeight(), matrix, true);
  }

  private void sendHttpSolveRequest(byte[] jpeg) {
    JsonObjectRequest req = new JsonObjectRequest(
        Request.Method.POST,
        SOLVE_URL,
        null,
        this::onHttpSuccessResponse,
        this::onHttpErrorResponse) {
      @Override
      public String getBodyContentType() {
        return "image/jpeg";
      }

      @Override
      public byte[] getBody() {
        return jpeg;
      }
    };
    req.setRetryPolicy(new DefaultRetryPolicy(30_000, 0, 0));
    httpQueue.add(req);
  }

  private void onHttpSuccessResponse(JSONObject response) {
    Log.d("SetSolver", "Solve response: " + response);
    try {
      detectedCards = new ArrayMap<>(12);

      JSONObject cardMap = response.getJSONObject("cards");
      Iterator<String> cardLabels = cardMap.keys();
      while (cardLabels.hasNext()) {
        String cardLabel = cardLabels.next();
        JSONArray cardArray = cardMap.getJSONArray(cardLabel);
        int left = cardArray.getJSONArray(0).getInt(0);
        int top = cardArray.getJSONArray(0).getInt(1);
        int right = cardArray.getJSONArray(2).getInt(0);
        int bottom = cardArray.getJSONArray(2).getInt(1);
        detectedCards.put(cardLabel, new Rect(left, top, right, bottom));
      }

      Map<String, List<Integer>> sets = new ArrayMap<>(12);
      JSONArray setsArray = response.getJSONArray("sets");
      for (int s = 0; s < setsArray.length(); s++) {
        JSONArray set = setsArray.getJSONArray(s);
        sets.computeIfAbsent(set.getString(0), k -> new ArrayList<>()).add(s);
        sets.computeIfAbsent(set.getString(1), k -> new ArrayList<>()).add(s);
        sets.computeIfAbsent(set.getString(2), k -> new ArrayList<>()).add(s);
      }

      Canvas canvas = new Canvas(photoBitmap);
      Paint paint = new Paint();
      paint.setStrokeWidth(SET_HIGHLIGHT_WIDTH);
      paint.setStyle(Paint.Style.STROKE);

      for (Map.Entry<String, List<Integer>> e : sets.entrySet()) {
        Rect drawRect = new Rect(detectedCards.get(e.getKey()));
        for (int s : e.getValue()) {
          paint.setColor(SET_HIGHLIGHT_COLORS[s]);
          canvas.drawRect(drawRect, paint);
          drawRect.inset(-SET_HIGHLIGHT_WIDTH, -SET_HIGHLIGHT_WIDTH);
        }
      }

      binding.imageView.setImageBitmap(photoBitmap);
    } catch (JSONException e) {
      showUnexpectedFailureSnackbar("Failure parsing HTTP response", e);
    }

    enableScanButton();
  }

  private void onHttpErrorResponse(VolleyError error) {
    Log.d("SetSolver", "Solve error response: " + error);
    showUnexpectedFailureSnackbar("Failure in HTTP response", null);
    enableScanButton();
  }

  private void showUnexpectedFailureSnackbar(String logMessage, Exception e) {
    Log.e("SetSolver", logMessage, e);
    Snackbar.make(binding.getRoot(), R.string.unexpected_failure, Snackbar.LENGTH_LONG).show();
  }

  private void disableScanButton() {
    binding.scan.setVisibility(View.INVISIBLE);
    binding.progressBar.setVisibility(View.VISIBLE);
  }

  private void enableScanButton() {
    binding.scan.setVisibility(View.VISIBLE);
    binding.progressBar.setVisibility(View.INVISIBLE);
  }
}