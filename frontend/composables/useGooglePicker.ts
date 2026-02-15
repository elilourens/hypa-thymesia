import { ref } from 'vue'

export const useGooglePicker = () => {
  const pickerLoaded = ref(false)
  const selectedFolder = ref<{ id: string, name: string } | null>(null)

  /**
   * Load Google Picker API.
   */
  const loadPicker = async (): Promise<void> => {
    return new Promise((resolve, reject) => {
      if (pickerLoaded.value) {
        resolve()
        return
      }

      // @ts-ignore - gapi loaded from CDN
      if (typeof window.gapi === 'undefined') {
        const error = new Error('Google API not loaded')
        console.error(error)
        reject(error)
        return
      }

      // @ts-ignore - gapi loaded from CDN
      window.gapi.load('picker', {
        callback: () => {
          pickerLoaded.value = true
          resolve()
        },
        onerror: (err: any) => {
          const error = new Error('Failed to load Google Picker API')
          console.error(error, err)
          reject(error)
        }
      })
    })
  }

  /**
   * Open Google Picker to select a folder.
   */
  const openFolderPicker = async (
    accessToken: string,
    googleClientId: string
  ): Promise<{ id: string, name: string } | null> => {
    await loadPicker()

    if (!pickerLoaded.value) {
      console.error('Picker API not loaded')
      return null
    }

    return new Promise((resolve) => {
      // @ts-ignore - google.picker loaded from gapi
      const picker = new google.picker.PickerBuilder()
        .addView(
          new google.picker.DocsView(google.picker.ViewId.FOLDERS)
            .setSelectFolderEnabled(true)
        )
        .setOAuthToken(accessToken)
        .setDeveloperKey(googleClientId)
        .setCallback((data: any) => {
          if (data.action === google.picker.Action.PICKED) {
            // Validate response
            if (!data.docs || data.docs.length === 0) {
              console.error('Picker returned no documents')
              resolve(null)
              return
            }

            const folder = data.docs[0]
            if (!folder || !folder.id || !folder.name) {
              console.error('Invalid folder data from picker')
              resolve(null)
              return
            }

            const result = {
              id: folder.id,
              name: folder.name
            }
            selectedFolder.value = result
            resolve(result)
          } else if (data.action === google.picker.Action.CANCEL) {
            resolve(null)
          }
        })
        .build()

      picker.setVisible(true)
    })
  }

  return {
    pickerLoaded,
    selectedFolder,
    loadPicker,
    openFolderPicker
  }
}
