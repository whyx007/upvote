/* 注入到 WebView 页面的原生桥（每次页面加载后注入，内部幂等） */
(function () {
  if (window.__upvoteNativeReady) return;
  window.__upvoteNativeReady = true;

  function blobToBase64(blob) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        var result = String(reader.result || '');
        var comma = result.indexOf(',');
        resolve(comma >= 0 ? result.slice(comma + 1) : '');
      };
      reader.onerror = function () { reject(reader.error || new Error('read blob failed')); };
      reader.readAsDataURL(blob);
    });
  }

  window.UpvoteNative = {
    platform: 'android',
    saveBlob: async function (filename, blob, mime) {
      var b64 = await blobToBase64(blob);
      window.AndroidBridge.saveBase64(filename, mime || (blob && blob.type) || 'application/octet-stream', b64);
      return true;
    }
  };
})();