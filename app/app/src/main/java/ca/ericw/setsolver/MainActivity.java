package ca.ericw.setsolver;

import android.Manifest;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.provider.Settings;
import android.transition.Visibility;
import android.util.Log;
import android.view.View;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.FileProvider;

import com.android.volley.DefaultRetryPolicy;
import com.android.volley.Request;
import com.android.volley.RequestQueue;
import com.android.volley.RetryPolicy;
import com.android.volley.VolleyError;
import com.android.volley.VolleyLog;
import com.android.volley.toolbox.JsonObjectRequest;
import com.android.volley.toolbox.Volley;
import com.google.android.material.snackbar.Snackbar;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.UnsupportedEncodingException;
import java.net.URL;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;

import ca.ericw.setsolver.databinding.ActivityMainBinding;

public class MainActivity extends AppCompatActivity {

  private static final String SOLVE_URL = "https://ffkbmc379f.execute-api.us-east-2.amazonaws.com/Prod/solve";

  private final ActivityResultLauncher<Uri> capturePhoto = registerForActivityResult(
      new ActivityResultContracts.TakePicture(),
      this::onTakePhotoResult);

  private final ActivityResultLauncher<String> requestPermission = registerForActivityResult(
      new ActivityResultContracts.RequestPermission(),
      this::onCameraPermissionResult);

  private ActivityMainBinding binding;
  private RequestQueue httpQueue;

  private String capturedPhotoPath;

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);

    binding = ActivityMainBinding.inflate(getLayoutInflater());
    setContentView(binding.getRoot());

    binding.scan.setOnClickListener(this::onScanClick);

    httpQueue = Volley.newRequestQueue(this);
  }

  @Override
  protected void onStart() {
    super.onStart();
    requestPermission.launch(Manifest.permission.CAMERA);
    resetButtonState();
  }

  private void onScanClick(View v) {
    try {
      File storageDir = getExternalFilesDir(Environment.DIRECTORY_PICTURES);
      File image = File.createTempFile("cap_", ".jpg", storageDir);
      capturedPhotoPath = image.getAbsolutePath();
      Uri uri = FileProvider.getUriForFile(
          this,
          "ca.ericw.setsolver.fileprovider",
          image);
      capturePhoto.launch(uri);
    } catch (IOException e) {
      showUnexpectedFailureSnackbar("Failure creating temp image", e);
    }
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
      binding.scan.setVisibility(View.INVISIBLE);
      binding.progressBar.setVisibility(View.VISIBLE);

      showCapturedPhoto();
      byte[] jpeg = getScaledJpegBytes();
      if (jpeg != null) {
        sendHttpSolveRequest(jpeg);
      }
    } else {
      showUnexpectedFailureSnackbar("Failure capturing photo", null);
    }
  }

  private void showCapturedPhoto() {
    BitmapFactory.Options bmOptions = new BitmapFactory.Options();
    bmOptions.inJustDecodeBounds = true;
    BitmapFactory.decodeFile(capturedPhotoPath, bmOptions);

    int scaleFactor = Math.max(
        1,
        Math.min(
            bmOptions.outWidth / binding.imageView.getWidth(),
            bmOptions.outHeight / binding.imageView.getHeight()));

    bmOptions.inJustDecodeBounds = false;
    bmOptions.inSampleSize = scaleFactor;

    Bitmap bitmap = BitmapFactory.decodeFile(capturedPhotoPath, bmOptions);
    binding.imageView.setImageBitmap(bitmap);
  }

  private byte[] getScaledJpegBytes() {
    try {
      return Files.readAllBytes(FileSystems.getDefault().getPath(capturedPhotoPath));
    } catch (IOException e) {
      showUnexpectedFailureSnackbar("Failure reading JPEG", e);
      return null;
    }

    /* TODO: Can we realistically reduce bandwidth?

    BitmapFactory.Options bmOptions = new BitmapFactory.Options();
    Bitmap bitmap = BitmapFactory.decodeFile(capturedPhotoPath, bmOptions);

    int outWidth = bitmap.getWidth();
    int outHeight = bitmap.getHeight();

    int minDim = Math.min(bitmap.getWidth(), bitmap.getHeight());
    if (minDim > 1024) {
      double scale = 1024.0 / minDim;
      outWidth = (int)(bitmap.getWidth() * scale);
      outHeight = (int)(bitmap.getHeight() * scale);
    }

    Bitmap scaled = Bitmap.createScaledBitmap(bitmap, outWidth, outHeight, true);
    Log.e("SetSolver", "Outputting to " + outWidth + " x " + outHeight);
    ByteArrayOutputStream bos = new ByteArrayOutputStream();
    scaled.compress(Bitmap.CompressFormat.JPEG, 75, bos);
    byte[] b = bos.toByteArray();

    Bitmap bb = BitmapFactory.decodeByteArray(b, 0, b.length);
    binding.imageView.setImageBitmap(bitmap);

    return b;
    */
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
    Log.e("SetSolver", response.toString());
    resetButtonState();
  }

  private void onHttpErrorResponse(VolleyError error) {
    showUnexpectedFailureSnackbar("Failure in HTTP response", null);
    resetButtonState();
  }

  private void showUnexpectedFailureSnackbar(String logMessage, Exception e) {
    Log.e("SetSolver", logMessage, e);
    Snackbar.make(binding.getRoot(), R.string.unexpected_failure, Snackbar.LENGTH_LONG).show();
  }

  private void resetButtonState() {
    binding.scan.setVisibility(View.VISIBLE);
    binding.progressBar.setVisibility(View.INVISIBLE);
  }
}